# Instagram Profile Downloader

Uma ferramenta simples para baixar e organizar mídias de perfis do Instagram.

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge\&logo=python\&logoColor=white)
![Tkinter](https://img.shields.io/badge/Tkinter-FFCA28?style=for-the-badge\&logo=python\&logoColor=black)
![Instaloader](https://img.shields.io/badge/Instaloader-C13584?style=for-the-badge\&logo=instagram\&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge\&logo=windows11\&logoColor=white)

---

## 📌 Sobre o Projeto

**Instagram Profile Downloader** é uma ferramenta em Python para baixar fotos, vídeos, carrosséis, Reels e outros conteúdos de perfis do Instagram.

Ela inclui uma interface gráfica simples para uso cotidiano e uma versão por linha de comando para scripts e automações. Os downloads são organizados automaticamente por perfil e tipo de mídia, mantendo tudo organizado e fácil de encontrar.

---

## ✨ Funcionalidades

* 📷 Baixe fotos, vídeos, carrosséis e fotos de perfil;
* 🎬 O modo completo também inclui Reels, stories atuais, destaques, publicações marcadas e IGTV;
* 🔐 Acesse perfis privados que já são seguidos pela conta conectada;
* 🌐 Reutilize sessões existentes do Brave, Chrome, Edge ou Firefox;
* 🛡️ Faça login por meio de uma janela isolada do Brave sem enviar sua senha para o aplicativo;
* 🔢 Suporte à autenticação em dois fatores;
* ⚡ Atualize downloads existentes sem baixar tudo novamente;
* 🗂️ Organize automaticamente imagens, vídeos e informações do perfil;
* 👥 Baixe vários perfis em uma única execução pelo terminal;
* 🖥️ Inclui uma interface gráfica com acompanhamento de progresso e logs de atividade.

---

## 🛠️ Tecnologias

| Tecnologia      | Utilizada para                             |
| --------------- | ------------------------------------------ |
| Python          | Lógica principal da aplicação              |
| Tkinter         | Interface gráfica                          |
| Instaloader     | Acesso e download de conteúdo do Instagram |
| browser-cookie3 | Leitura de sessões locais dos navegadores  |
| WebSocket/CDP   | Login isolado pelo Brave                   |
| unittest        | Testes automatizados                       |

---

## 🚀 Instalação

### Requisitos

* Windows;
* Python 3.10 ou superior;
* Uma conta do Instagram para perfis privados ou para utilizar o modo completo.

Abra o PowerShell dentro da pasta do projeto e execute:

```powershell
py -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

python -m pip install -r requirements.txt
```

Se o PowerShell bloquear a ativação do ambiente virtual, você pode instalar as dependências diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## ▶️ Como Usar

### Interface Gráfica

Clique duas vezes em `abrir_interface.bat` ou execute:

```powershell
.\.venv\Scripts\python.exe interface.py
```

Dentro do aplicativo:

1. Informe o nome de usuário do perfil, `@usuario` ou a URL do perfil;
2. Escolha onde os arquivos devem ser salvos;
3. Ative o login caso queira acessar um perfil privado ou utilizar o modo completo;
4. Escolha uma sessão do navegador ou entre com a sua conta;
5. Clique em **Baixar Perfil**.

O login pelo navegador é a opção recomendada. Ao utilizar o Brave, o aplicativo abre uma janela separada do navegador para que você possa fazer login diretamente pelo Instagram.

### Terminal

Baixar conteúdo público de um perfil:

```powershell
python baixar_perfil.py usuario
```

Baixar vários perfis:

```powershell
python baixar_perfil.py @perfil1 https://www.instagram.com/perfil2/
```

Baixar todo o conteúdo disponível utilizando uma sessão do navegador:

```powershell
python baixar_perfil.py perfil_alvo --navegador brave --completo
```

Você também pode entrar utilizando sua conta do Instagram. A senha será solicitada sem ser exibida no terminal:

```powershell
python baixar_perfil.py perfil_alvo --login sua_conta --completo
```

Atualizar um download existente e escolher uma pasta de saída diferente:

```powershell
python baixar_perfil.py perfil_alvo --navegador brave --completo --atualizar --saida D:\Instagram
```

Ver todas as opções disponíveis:

```powershell
python baixar_perfil.py --help
```

---

## 📁 Organização dos Arquivos

Por padrão, o conteúdo baixado é salvo dentro de `downloads/`:

```text
downloads/
└── perfil_alvo/
    ├── imagens/
    │   ├── foto.jpg
    │   └── imagem_carrossel.jpg
    ├── videos/
    │   └── video_ou_reel.mp4
    └── dados_do_perfil.txt
```

O arquivo `dados_do_perfil.txt` contém informações públicas do perfil, como nome de exibição, nome de usuário, biografia, categoria, site e estatísticas do perfil.

---

## 🧪 Testes

Execute a suíte de testes automatizados com:

```powershell
python -m unittest discover -s tests -v
```

---

## ⚠️ Segurança e Limitações

* Utilize a ferramenta apenas para arquivar conteúdos aos quais você possui permissão de acesso;
* Perfis privados só podem ser baixados se a conta conectada já os seguir;
* Stories expirados não podem ser recuperados;
* O Instagram pode solicitar CAPTCHA, confirmação de segurança ou limitar temporariamente as requisições;
* As senhas não são salvas;
* As sessões locais são armazenadas dentro de `.sessions/` e devem ser tratadas como credenciais de acesso;
* Nunca compartilhe a pasta `.sessions/` nem faça commit dela no Git;
* O Instaloader é um projeto independente e não utiliza uma API oficial do Instagram.

Utilize a ferramenta com responsabilidade e respeite a privacidade de outras pessoas, os direitos autorais e os Termos de Uso do Instagram.
