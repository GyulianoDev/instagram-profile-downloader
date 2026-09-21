# Instagram Profile Downloader

A simple tool for downloading and organizing media from Instagram profiles.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge\&logo=python\&logoColor=white) ![Tkinter](https://img.shields.io/badge/Tkinter-FFCA28?style=for-the-badge\&logo=python\&logoColor=black) ![Instaloader](https://img.shields.io/badge/Instaloader-C13584?style=for-the-badge\&logo=instagram\&logoColor=white) ![Windows](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge\&logo=windows11\&logoColor=white)

---

## 📌 About the Project

**Instagram Profile Downloader** is a Python tool for downloading photos, videos, carousels, Reels, and other content from Instagram profiles.

It includes a simple graphical interface for everyday use and a command-line version for scripts and automation. Downloads are automatically organized by profile and media type, so everything stays clean and easy to find.

---

## ✨ Features

* 📷 Download photos, videos, carousels, and profile pictures;
* 🎬 Full mode also includes Reels, current stories, highlights, tagged posts, and IGTV;
* 🔐 Access private profiles already followed by the logged-in account;
* 🌐 Reuse existing sessions from Brave, Chrome, Edge, or Firefox;
* 🛡️ Log in through an isolated Brave window without sending your password to the app;
* 🔢 Supports two-factor authentication;
* ⚡ Update existing downloads without downloading everything again;
* 🗂️ Automatically organize images, videos, and profile information;
* 👥 Download multiple profiles in a single terminal run;
* 🖥️ Includes a graphical interface with progress tracking and activity logs.

---

## 🛠️ Technologies

| Technology      | Used for                               |
| --------------- | -------------------------------------- |
| Python          | Main application logic                 |
| Tkinter         | Graphical interface                    |
| Instaloader     | Instagram content access and downloads |
| browser-cookie3 | Reading local browser sessions         |
| WebSocket/CDP   | Isolated Brave login                   |
| unittest        | Automated tests                        |

---

## 🚀 Installation

### Requirements

* Windows;
* Python 3.10 or newer;
* An Instagram account for private profiles or full mode.

Open PowerShell inside the project folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks the virtual environment activation, you can install the dependencies directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## ▶️ How to Use

### Graphical Interface

Double-click `open_interface.bat` or run:

```powershell
.\.venv\Scripts\python.exe interface.py
```

Inside the app:

1. Enter the profile username, `@username`, or profile URL;
2. Choose where the files should be saved;
3. Enable login if you want to access a private profile or use full mode;
4. Choose a browser session or log in with your account;
5. Click **Download Profile**.

Browser login is the recommended option. When using Brave, the app opens a separate browser window where you can log in directly through Instagram.

### Terminal

Download public content from a profile:

```powershell
python download_profile.py username
```

Download multiple profiles:

```powershell
python download_profile.py @profile1 https://www.instagram.com/profile2/
```

Download all available content using a browser session:

```powershell
python download_profile.py target_profile --navegador brave --completo
```

You can also log in with your Instagram account. The password will be requested without being displayed in the terminal:

```powershell
python download_profile.py target_profile --login your_account --completo
```

Update an existing download and choose a different output folder:

```powershell
python download_profile.py target_profile --navegador brave --completo --atualizar --saida D:\Instagram
```

See all available options:

```powershell
python download_profile.py --help
```

---

## 📁 File Organization

By default, downloaded content is saved inside `downloads/`:

```text
downloads/
└── target_profile/
    ├── imagens/
    │   ├── photo.jpg
    │   └── carousel_image.jpg
    ├── videos/
    │   └── video_or_reel.mp4
    └── dados_do_perfil.txt
```

The `dados_do_perfil.txt` file contains public profile information such as the display name, username, bio, category, website, and profile statistics.

---

<img width="754" height="783" alt="image" src="https://github.com/user-attachments/assets/aea6270c-2b61-473e-90d6-07aff7bf462d" />

---

## 🧪 Tests

Run the automated test suite with:

```powershell
python -m unittest discover -s tests -v
```

---

## ⚠️ Security and Limitations

* Only use the tool to archive content you are allowed to access;
* Private profiles can only be downloaded if the logged-in account already follows them;
* Expired stories cannot be recovered;
* Instagram may request a CAPTCHA, security confirmation, or temporarily limit requests;
* Passwords are not saved;
* Local sessions are stored inside `.sessions/` and should be treated like login credentials;
* Never share the `.sessions/` folder or commit it to Git;
* Instaloader is an independent project and does not use an official Instagram API.

Use the tool responsibly and respect other people's privacy, copyright, and Instagram's Terms of Use.
