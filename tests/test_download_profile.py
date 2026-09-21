import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from download_profile import (
    Configuration,
    _open_brave_login,
    _load_saved_brave_session,
    _execute_cdp_command,
    session_file,
    run,
    extract_checkpoint_url,
    normalize_login,
    normalize_profile,
    profile_download_options,
    instaloader_options,
    get_compatible_profile,
    organize_profile_folder,
    remove_duplicates,
    save_profile_data,
)


class ProfileNormalizationTest(unittest.TestCase):
    def test_accepts_common_formats(self) -> None:
        cases = {
            "OpenAI": "openai",
            "@OpenAI": "openai",
            r"@by\_raquelvitoria": "by_raquelvitoria",
            " https://www.instagram.com/OpenAI/ ": "openai",
        }
        for input_value, expected in cases.items():
            with self.subTest(input_value=input_value):
                self.assertEqual(normalize_profile(input_value), expected)

    def test_rejects_post_url(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            normalize_profile("https://www.instagram.com/p/ABC123/")

    def test_rejects_path_characters(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            normalize_profile("../secret")

    def test_removes_duplicates_preserving_order(self) -> None:
        self.assertEqual(remove_duplicates(["one", "two", "one"]), ("one", "two"))

    def test_login_accepts_username_or_email(self) -> None:
        self.assertEqual(normalize_login("@OpenAI"), "openai")
        self.assertEqual(normalize_login(" Person@Example.com "), "person@example.com")

    def test_session_file_does_not_expose_email(self) -> None:
        path = session_file("person@example.com")
        self.assertNotIn("person", path.name)
        self.assertNotIn("@", path.name)

    def test_extracts_checkpoint_and_completes_official_url(self) -> None:
        message = (
            "Login: Checkpoint required. Point your browser to "
            "/auth_platform/?token=abc123 - follow the instructions, then retry."
        )
        self.assertEqual(
            extract_checkpoint_url(message),
            "https://www.instagram.com/auth_platform/?token=abc123",
        )

    def test_common_message_is_not_checkpoint(self) -> None:
        self.assertIsNone(extract_checkpoint_url("Login error: Wrong password."))

    def test_checkpoint_never_opens_external_domain(self) -> None:
        message = "Point your browser to https://example.com/fake - follow"
        self.assertIsNone(extract_checkpoint_url(message))

    @patch("download_profile._free_local_port", return_value=45678)
    @patch("download_profile._wait_for_brave_websocket", return_value="ws://127.0.0.1/devtools")
    @patch("download_profile._close_isolated_brave")
    @patch("download_profile.tempfile.mkdtemp", return_value="temporary_test_profile")
    @patch("download_profile._find_brave", return_value=Path("brave.exe"))
    @patch("download_profile.subprocess.Popen")
    def test_brave_login_opens_single_window(
        self,
        open_process: Mock,
        _find: Mock,
        _folder: Mock,
        close: Mock,
        _wait: Mock,
        _port: Mock,
    ) -> None:
        class LoginError(Exception):
            pass

        connection = Mock()
        connection.recv.return_value = json.dumps(
            {
                "id": 1,
                "result": {
                    "cookies": [
                        {"name": "sessionid", "value": "secret", "domain": ".instagram.com"},
                        {"name": "other", "value": "ignore", "domain": ".example.com"},
                    ]
                },
            }
        )
        fake_websocket = SimpleNamespace(create_connection=Mock(return_value=connection))
        process = Mock(pid=1234)
        process.poll.return_value = None
        open_process.return_value = process
        module = SimpleNamespace(
            exceptions=SimpleNamespace(
                LoginException=LoginError,
                InstaloaderException=LoginError,
            )
        )
        with patch.dict("sys.modules", {"websocket": fake_websocket}):
            cookies = _open_brave_login(module, lambda _message: None)

        open_process.assert_called_once()
        self.assertIn(
            "https://www.instagram.com/accounts/login/",
            open_process.call_args.args[0],
        )
        self.assertEqual(cookies, {"sessionid": "secret"})
        close.assert_called_once()

    def test_cdp_command_ignores_events_and_waits_for_correct_response(self) -> None:
        connection = Mock()
        connection.recv.side_effect = [
            json.dumps({"method": "Network.event"}),
            json.dumps({"id": 7, "result": {"cookies": []}}),
        ]
        result = _execute_cdp_command(connection, 7, "Storage.getCookies")
        self.assertEqual(result, {"cookies": []})
        connection.send.assert_called_once()

    def test_uses_exact_search_when_instagram_schema_was_removed(self) -> None:
        class InstaloaderError(Exception):
            pass

        correct_profile = SimpleNamespace(username="by_raquelvitoria")
        similar_profile = SimpleNamespace(username="by_raquelvitoria_fan")
        from_username = Mock(
            side_effect=InstaloaderError(
                "Asset asset://laser.provider/ig_business_category_subvertical has been deleted"
            )
        )
        module = SimpleNamespace(
            Profile=SimpleNamespace(from_username=from_username),
            TopSearchResults=Mock(
                return_value=SimpleNamespace(
                    get_profiles=lambda: iter([similar_profile, correct_profile])
                )
            ),
            exceptions=SimpleNamespace(
                InstaloaderException=InstaloaderError,
                ProfileNotExistsException=InstaloaderError,
            ),
        )

        context = SimpleNamespace(is_logged_in=False)
        profile = get_compatible_profile(
            module, context, "by_raquelvitoria", lambda _m: None
        )
        self.assertIs(profile, correct_profile)

    def test_with_login_avoids_endpoint_with_removed_schema(self) -> None:
        correct_profile = SimpleNamespace(username="by_raquelvitoria")
        from_username = Mock()
        module = SimpleNamespace(
            Profile=SimpleNamespace(from_username=from_username),
            TopSearchResults=Mock(
                return_value=SimpleNamespace(
                    get_profiles=lambda: iter([correct_profile])
                )
            ),
            exceptions=SimpleNamespace(ProfileNotExistsException=Exception),
        )

        profile = get_compatible_profile(
            module,
            SimpleNamespace(is_logged_in=True),
            "by_raquelvitoria",
            lambda _m: None,
        )
        self.assertIs(profile, correct_profile)
        from_username.assert_not_called()

    def test_does_not_hide_other_error_when_getting_profile(self) -> None:
        class InstaloaderError(Exception):
            pass

        module = SimpleNamespace(
            Profile=SimpleNamespace(from_username=Mock(side_effect=InstaloaderError("401"))),
            exceptions=SimpleNamespace(InstaloaderException=InstaloaderError),
        )
        with self.assertRaisesRegex(InstaloaderError, "401"):
            get_compatible_profile(
                module,
                SimpleNamespace(is_logged_in=False),
                "profile",
                lambda _m: None,
            )

    @patch("download_profile.BRAVE_SESSION_FILE")
    def test_reuses_single_saved_brave_session(self, brave_file: Mock) -> None:
        brave_file.exists.return_value = True
        loader = Mock()
        loader.test_login.return_value = "test_account"
        module = SimpleNamespace(
            exceptions=SimpleNamespace(InstaloaderException=Exception)
        )

        reused = _load_saved_brave_session(
            module, loader, lambda _message: None
        )
        self.assertTrue(reused)
        self.assertEqual(loader.context.username, "test_account")


class InstaloaderConfigurationTest(unittest.TestCase):
    def test_organizes_files_and_enables_media(self) -> None:
        config = Configuration(profiles=("openai",), output=Path("downloads"))
        options = instaloader_options(config)

        self.assertEqual(options["dirname_pattern"], str(Path("downloads") / "{target}"))
        self.assertEqual(options["filename_pattern"], "{shortcode}")
        self.assertTrue(options["download_pictures"])
        self.assertTrue(options["download_videos"])
        self.assertFalse(options["download_video_thumbnails"])
        self.assertFalse(options["download_comments"])
        self.assertFalse(options["save_metadata"])
        self.assertEqual(options["post_metadata_txt_pattern"], "")
        self.assertEqual(options["storyitem_metadata_txt_pattern"], "")
        self.assertIsNone(options["resume_prefix"])
        self.assertTrue(options["sanitize_paths"])

    def test_password_is_not_part_of_persistent_configuration(self) -> None:
        self.assertNotIn("password", Configuration.__dataclass_fields__)

    def test_organizer_separates_media_and_removes_auxiliary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            old = profile / "tagged" / "media" / "2026"
            old.mkdir(parents=True)
            (old / "photo.jpg").write_bytes(b"image")
            (old / "reel.mp4").write_bytes(b"video")
            (old / "post.json").write_text("{}", encoding="utf-8")
            (old / "caption.txt").write_text("caption", encoding="utf-8")
            (profile / "profile_data.txt").write_text("data", encoding="utf-8")

            images, videos = organize_profile_folder(profile)

            self.assertEqual((images, videos), (1, 1))
            self.assertEqual((profile / "images" / "photo.jpg").read_bytes(), b"image")
            self.assertEqual((profile / "videos" / "reel.mp4").read_bytes(), b"video")
            self.assertTrue((profile / "profile_data.txt").exists())
            self.assertFalse(any(profile.rglob("*.json")))
            self.assertEqual(
                sorted(item.name for item in profile.iterdir()),
                ["images", "profile_data.txt", "videos"],
            )

    def test_saves_single_txt_with_profile_data(self) -> None:
        profile = SimpleNamespace(
            _obtain_metadata=Mock(),
            _node={
                "city_name": "São Paulo",
                "region_name": "SP",
                "business_category_name": "Content creator",
                "public_email": "contact@example.com",
            },
            username="test_profile",
            full_name="Test Profile",
            external_url="https://example.com",
            followers=120,
            followees=30,
            mediacount=15,
            is_private=False,
            is_verified=True,
            biography="My biography",
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = save_profile_data(profile, Path(temporary))
            content = destination.read_text(encoding="utf-8")

        self.assertEqual(destination.name, "profile_data.txt")
        self.assertIn("Name: Test Profile", content)
        self.assertIn("City: São Paulo, SP", content)
        self.assertIn("Biography:\nMy biography", content)

    def test_public_mode_does_not_query_dedicated_reels_endpoint(self) -> None:
        config = Configuration(profiles=("openai",), output=Path("downloads"))
        self.assertFalse(profile_download_options(config)["reels"])

    def test_full_mode_with_login_includes_reels(self) -> None:
        config = Configuration(
            profiles=("openai",),
            output=Path("downloads"),
            login="test_account",
            full=True,
        )
        self.assertTrue(profile_download_options(config)["reels"])

    def test_configuration_accepts_browser_session(self) -> None:
        config = Configuration(
            profiles=("openai",),
            output=Path("downloads"),
            browser="chrome",
            full=True,
        )
        self.assertEqual(config.browser, "chrome")
        self.assertTrue(profile_download_options(config)["reels"])

    def test_configuration_accepts_brave(self) -> None:
        config = Configuration(
            profiles=("openai",),
            output=Path("downloads"),
            browser="brave",
            full=True,
        )
        self.assertEqual(config.browser, "brave")

    def test_full_content_without_login_fails_before_network_access(self) -> None:
        messages: list[str] = []
        config = Configuration(
            profiles=("openai",),
            output=Path("downloads"),
            full=True,
        )

        self.assertEqual(run(config, logger=messages.append), 2)
        self.assertTrue(any("requires login" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
