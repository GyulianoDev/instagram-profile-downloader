import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from baixar_perfil import (
    Configuracao,
    _abrir_login_brave,
    _carregar_sessao_brave_salva,
    _executar_comando_cdp,
    arquivo_de_sessao,
    executar,
    extrair_url_checkpoint,
    normalizar_login,
    normalizar_perfil,
    opcoes_download_perfil,
    opcoes_instaloader,
    obter_perfil_compativel,
    organizar_pasta_do_perfil,
    remover_duplicados,
    salvar_dados_do_perfil,
)


class NormalizacaoDePerfilTest(unittest.TestCase):
    def test_aceita_formatos_comuns(self) -> None:
        casos = {
            "OpenAI": "openai",
            "@OpenAI": "openai",
            r"@by\_raquelvitoria": "by_raquelvitoria",
            " https://www.instagram.com/OpenAI/ ": "openai",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_perfil(entrada), esperado)

    def test_rejeita_url_de_publicacao(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            normalizar_perfil("https://www.instagram.com/p/ABC123/")

    def test_rejeita_caracteres_de_caminho(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            normalizar_perfil("../segredo")

    def test_remove_duplicados_preservando_ordem(self) -> None:
        self.assertEqual(remover_duplicados(["um", "dois", "um"]), ("um", "dois"))

    def test_login_aceita_usuario_ou_email(self) -> None:
        self.assertEqual(normalizar_login("@OpenAI"), "openai")
        self.assertEqual(normalizar_login(" Pessoa@Example.com "), "pessoa@example.com")

    def test_arquivo_de_sessao_nao_expoe_email(self) -> None:
        caminho = arquivo_de_sessao("pessoa@example.com")
        self.assertNotIn("pessoa", caminho.name)
        self.assertNotIn("@", caminho.name)

    def test_extrai_checkpoint_e_completa_url_oficial(self) -> None:
        mensagem = (
            "Login: Checkpoint required. Point your browser to "
            "/auth_platform/?token=abc123 - follow the instructions, then retry."
        )
        self.assertEqual(
            extrair_url_checkpoint(mensagem),
            "https://www.instagram.com/auth_platform/?token=abc123",
        )

    def test_mensagem_comum_nao_e_checkpoint(self) -> None:
        self.assertIsNone(extrair_url_checkpoint("Login error: Wrong password."))

    def test_checkpoint_nunca_abre_dominio_externo(self) -> None:
        mensagem = "Point your browser to https://example.com/falso - follow"
        self.assertIsNone(extrair_url_checkpoint(mensagem))

    @patch("baixar_perfil._porta_local_livre", return_value=45678)
    @patch("baixar_perfil._aguardar_websocket_brave", return_value="ws://127.0.0.1/devtools")
    @patch("baixar_perfil._encerrar_brave_isolado")
    @patch("baixar_perfil.tempfile.mkdtemp", return_value="perfil_temporario_teste")
    @patch("baixar_perfil._localizar_brave", return_value=Path("brave.exe"))
    @patch("baixar_perfil.subprocess.Popen")
    def test_login_brave_abre_uma_unica_janela(
        self,
        abrir_processo: Mock,
        _localizar: Mock,
        _pasta: Mock,
        encerrar: Mock,
        _aguardar: Mock,
        _porta: Mock,
    ) -> None:
        class ErroDeLogin(Exception):
            pass

        conexao = Mock()
        conexao.recv.return_value = json.dumps(
            {
                "id": 1,
                "result": {
                    "cookies": [
                        {"name": "sessionid", "value": "segredo", "domain": ".instagram.com"},
                        {"name": "outro", "value": "ignorar", "domain": ".example.com"},
                    ]
                },
            }
        )
        websocket_falso = SimpleNamespace(create_connection=Mock(return_value=conexao))
        processo = Mock(pid=1234)
        processo.poll.return_value = None
        abrir_processo.return_value = processo
        modulo = SimpleNamespace(
            exceptions=SimpleNamespace(
                LoginException=ErroDeLogin,
                InstaloaderException=ErroDeLogin,
            )
        )
        with patch.dict("sys.modules", {"websocket": websocket_falso}):
            cookies = _abrir_login_brave(modulo, lambda _mensagem: None)

        abrir_processo.assert_called_once()
        self.assertIn(
            "https://www.instagram.com/accounts/login/",
            abrir_processo.call_args.args[0],
        )
        self.assertEqual(cookies, {"sessionid": "segredo"})
        encerrar.assert_called_once()

    def test_comando_cdp_ignora_eventos_e_espera_resposta_correta(self) -> None:
        conexao = Mock()
        conexao.recv.side_effect = [
            json.dumps({"method": "Network.evento"}),
            json.dumps({"id": 7, "result": {"cookies": []}}),
        ]
        resultado = _executar_comando_cdp(conexao, 7, "Storage.getCookies")
        self.assertEqual(resultado, {"cookies": []})
        conexao.send.assert_called_once()

    def test_usa_busca_exata_quando_schema_do_instagram_foi_removido(self) -> None:
        class ErroInstaloader(Exception):
            pass

        perfil_correto = SimpleNamespace(username="by_raquelvitoria")
        perfil_parecido = SimpleNamespace(username="by_raquelvitoria_fan")
        from_username = Mock(
            side_effect=ErroInstaloader(
                "Asset asset://laser.provider/ig_business_category_subvertical has been deleted"
            )
        )
        modulo = SimpleNamespace(
            Profile=SimpleNamespace(from_username=from_username),
            TopSearchResults=Mock(
                return_value=SimpleNamespace(
                    get_profiles=lambda: iter([perfil_parecido, perfil_correto])
                )
            ),
            exceptions=SimpleNamespace(
                InstaloaderException=ErroInstaloader,
                ProfileNotExistsException=ErroInstaloader,
            ),
        )

        contexto = SimpleNamespace(is_logged_in=False)
        perfil = obter_perfil_compativel(
            modulo, contexto, "by_raquelvitoria", lambda _m: None
        )
        self.assertIs(perfil, perfil_correto)

    def test_com_login_evitar_endpoint_com_schema_removido(self) -> None:
        perfil_correto = SimpleNamespace(username="by_raquelvitoria")
        from_username = Mock()
        modulo = SimpleNamespace(
            Profile=SimpleNamespace(from_username=from_username),
            TopSearchResults=Mock(
                return_value=SimpleNamespace(
                    get_profiles=lambda: iter([perfil_correto])
                )
            ),
            exceptions=SimpleNamespace(ProfileNotExistsException=Exception),
        )

        perfil = obter_perfil_compativel(
            modulo,
            SimpleNamespace(is_logged_in=True),
            "by_raquelvitoria",
            lambda _m: None,
        )
        self.assertIs(perfil, perfil_correto)
        from_username.assert_not_called()

    def test_nao_esconde_outro_erro_ao_obter_perfil(self) -> None:
        class ErroInstaloader(Exception):
            pass

        modulo = SimpleNamespace(
            Profile=SimpleNamespace(from_username=Mock(side_effect=ErroInstaloader("401"))),
            exceptions=SimpleNamespace(InstaloaderException=ErroInstaloader),
        )
        with self.assertRaisesRegex(ErroInstaloader, "401"):
            obter_perfil_compativel(
                modulo,
                SimpleNamespace(is_logged_in=False),
                "perfil",
                lambda _m: None,
            )

    @patch("baixar_perfil.ARQUIVO_SESSAO_BRAVE")
    def test_reutiliza_sessao_unica_salva_do_brave(self, arquivo_brave: Mock) -> None:
        arquivo_brave.exists.return_value = True
        loader = Mock()
        loader.test_login.return_value = "conta_teste"
        modulo = SimpleNamespace(
            exceptions=SimpleNamespace(InstaloaderException=Exception)
        )

        reutilizada = _carregar_sessao_brave_salva(
            modulo, loader, lambda _mensagem: None
        )
        self.assertTrue(reutilizada)
        self.assertEqual(loader.context.username, "conta_teste")


class ConfiguracaoDoInstaloaderTest(unittest.TestCase):
    def test_organiza_arquivos_e_habilita_midias(self) -> None:
        config = Configuracao(perfis=("openai",), saida=Path("downloads"))
        opcoes = opcoes_instaloader(config)

        self.assertEqual(opcoes["dirname_pattern"], str(Path("downloads") / "{target}"))
        self.assertEqual(opcoes["filename_pattern"], "{shortcode}")
        self.assertTrue(opcoes["download_pictures"])
        self.assertTrue(opcoes["download_videos"])
        self.assertFalse(opcoes["download_video_thumbnails"])
        self.assertFalse(opcoes["download_comments"])
        self.assertFalse(opcoes["save_metadata"])
        self.assertEqual(opcoes["post_metadata_txt_pattern"], "")
        self.assertEqual(opcoes["storyitem_metadata_txt_pattern"], "")
        self.assertIsNone(opcoes["resume_prefix"])
        self.assertTrue(opcoes["sanitize_paths"])

    def test_senha_nao_faz_parte_da_configuracao_persistente(self) -> None:
        self.assertNotIn("senha", Configuracao.__dataclass_fields__)

    def test_organizador_separa_midias_e_remove_auxiliares(self) -> None:
        with tempfile.TemporaryDirectory() as temporaria:
            perfil = Path(temporaria) / "perfil"
            antiga = perfil / "tagged" / "midia" / "2026"
            antiga.mkdir(parents=True)
            (antiga / "foto.jpg").write_bytes(b"imagem")
            (antiga / "reel.mp4").write_bytes(b"video")
            (antiga / "post.json").write_text("{}", encoding="utf-8")
            (antiga / "legenda.txt").write_text("legenda", encoding="utf-8")
            (perfil / "dados_do_perfil.txt").write_text("dados", encoding="utf-8")

            imagens, videos = organizar_pasta_do_perfil(perfil)

            self.assertEqual((imagens, videos), (1, 1))
            self.assertEqual((perfil / "imagens" / "foto.jpg").read_bytes(), b"imagem")
            self.assertEqual((perfil / "videos" / "reel.mp4").read_bytes(), b"video")
            self.assertTrue((perfil / "dados_do_perfil.txt").exists())
            self.assertFalse(any(perfil.rglob("*.json")))
            self.assertEqual(
                sorted(item.name for item in perfil.iterdir()),
                ["dados_do_perfil.txt", "imagens", "videos"],
            )

    def test_salva_um_unico_txt_com_dados_do_perfil(self) -> None:
        perfil = SimpleNamespace(
            _obtain_metadata=Mock(),
            _node={
                "city_name": "São Paulo",
                "region_name": "SP",
                "business_category_name": "Criador de conteúdo",
                "public_email": "contato@example.com",
            },
            username="perfil_teste",
            full_name="Perfil Teste",
            external_url="https://example.com",
            followers=120,
            followees=30,
            mediacount=15,
            is_private=False,
            is_verified=True,
            biography="Minha biografia",
        )
        with tempfile.TemporaryDirectory() as temporaria:
            destino = salvar_dados_do_perfil(perfil, Path(temporaria))
            conteudo = destino.read_text(encoding="utf-8")

        self.assertEqual(destino.name, "dados_do_perfil.txt")
        self.assertIn("Nome: Perfil Teste", conteudo)
        self.assertIn("Cidade: São Paulo, SP", conteudo)
        self.assertIn("Biografia:\nMinha biografia", conteudo)

    def test_modo_publico_nao_consulta_endpoint_dedicado_de_reels(self) -> None:
        config = Configuracao(perfis=("openai",), saida=Path("downloads"))
        self.assertFalse(opcoes_download_perfil(config)["reels"])

    def test_modo_completo_com_login_inclui_reels(self) -> None:
        config = Configuracao(
            perfis=("openai",),
            saida=Path("downloads"),
            login="conta_teste",
            completo=True,
        )
        self.assertTrue(opcoes_download_perfil(config)["reels"])

    def test_configuracao_aceita_sessao_do_navegador(self) -> None:
        config = Configuracao(
            perfis=("openai",),
            saida=Path("downloads"),
            navegador="chrome",
            completo=True,
        )
        self.assertEqual(config.navegador, "chrome")
        self.assertTrue(opcoes_download_perfil(config)["reels"])

    def test_configuracao_aceita_brave(self) -> None:
        config = Configuracao(
            perfis=("openai",),
            saida=Path("downloads"),
            navegador="brave",
            completo=True,
        )
        self.assertEqual(config.navegador, "brave")

    def test_conteudo_completo_sem_login_falha_antes_de_acessar_a_rede(self) -> None:
        mensagens: list[str] = []
        config = Configuracao(
            perfis=("openai",),
            saida=Path("downloads"),
            completo=True,
        )

        self.assertEqual(executar(config, registrar=mensagens.append), 2)
        self.assertTrue(any("exige login" in mensagem for mensagem in mensagens))


if __name__ == "__main__":
    unittest.main()
