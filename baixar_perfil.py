from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.request import urlopen


PASTA_DO_PROJETO = Path(__file__).resolve().parent
PASTA_DE_SESSOES = PASTA_DO_PROJETO / ".sessions"
ARQUIVO_SESSAO_BRAVE = PASTA_DE_SESSOES / "brave.session"
PADRAO_DE_USUARIO = re.compile(r"[A-Za-z0-9._]{1,30}")
PADRAO_DE_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
)

Registrador = Callable[[str], None]
Solicitador = Callable[[], str]
ManipuladorDeCheckpoint = Callable[[str], None]


@dataclass(frozen=True)
class Configuracao:
    perfis: tuple[str, ...]
    saida: Path
    login: str | None = None
    navegador: str | None = None
    completo: bool = False
    atualizar: bool = False


def normalizar_perfil(valor: str) -> str:
    """Aceita @usuario, usuario ou a URL do perfil e retorna somente o usuário."""
    perfil = valor.strip()

    if "://" in perfil:
        url = urlparse(perfil)
        dominio = (url.hostname or "").lower()
        if dominio not in {"instagram.com", "www.instagram.com"}:
            raise argparse.ArgumentTypeError("a URL precisa ser de instagram.com")

        partes = [parte for parte in url.path.split("/") if parte]
        if len(partes) != 1:
            raise argparse.ArgumentTypeError("informe a URL de um perfil, não de uma publicação")
        perfil = partes[0]

    perfil = perfil.removeprefix("@").strip()
    # Aceita nomes copiados de textos Markdown, onde _ e . podem vir escapados.
    perfil = perfil.replace(r"\_", "_").replace(r"\.", ".")
    if not PADRAO_DE_USUARIO.fullmatch(perfil):
        raise argparse.ArgumentTypeError(
            "perfil inválido; use apenas letras, números, ponto e sublinhado"
        )
    return perfil.lower()


def remover_duplicados(perfis: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(perfis))


def normalizar_login(valor: str) -> str:
    """Aceita nome de usuário, @usuário ou e-mail usado no Instagram."""
    login = valor.strip()
    try:
        return normalizar_perfil(login)
    except argparse.ArgumentTypeError:
        pass

    if len(login) <= 254 and PADRAO_DE_EMAIL.fullmatch(login):
        return login.lower()
    raise argparse.ArgumentTypeError("informe seu usuário do Instagram ou um e-mail válido")


def arquivo_de_sessao(login: str) -> Path:
    # Evita expor usuário ou e-mail no nome do arquivo local.
    identificador = hashlib.sha256(login.encode("utf-8")).hexdigest()[:20]
    return PASTA_DE_SESSOES / f"{identificador}.session"


def extrair_url_checkpoint(mensagem: str) -> str | None:
    correspondencia = re.search(r"Point your browser to (\S+) - follow", mensagem)
    if not correspondencia:
        return None
    url = urljoin("https://www.instagram.com/", correspondencia.group(1))
    if (urlparse(url).hostname or "").lower() not in {"instagram.com", "www.instagram.com"}:
        return None
    return url


def opcoes_instaloader(configuracao: Configuracao) -> dict[str, Any]:
    return {
        "dirname_pattern": str(configuracao.saida / "{target}"),
        "filename_pattern": "{shortcode}",
        "title_pattern": "{date_utc:%Y-%m-%d_%H-%M-%S}_{typename}",
        "download_pictures": True,
        "download_videos": True,
        "download_video_thumbnails": False,
        "download_comments": False,
        "save_metadata": False,
        "post_metadata_txt_pattern": "",
        "storyitem_metadata_txt_pattern": "",
        "resume_prefix": None,
        "sanitize_paths": True,
        "quiet": True,
    }


EXTENSOES_DE_IMAGEM = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
EXTENSOES_DE_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}


def _arquivos_iguais(primeiro: Path, segundo: Path) -> bool:
    if primeiro.stat().st_size != segundo.stat().st_size:
        return False

    def resumo(caminho: Path) -> bytes:
        calculador = hashlib.sha256()
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                calculador.update(bloco)
        return calculador.digest()

    return resumo(primeiro) == resumo(segundo)


def _destino_sem_colisao(origem: Path, pasta: Path) -> Path:
    destino = pasta / origem.name
    if not destino.exists() or _arquivos_iguais(origem, destino):
        return destino
    contador = 2
    while True:
        candidato = pasta / f"{origem.stem}_{contador}{origem.suffix}"
        if not candidato.exists() or _arquivos_iguais(origem, candidato):
            return candidato
        contador += 1


def organizar_pasta_do_perfil(pasta_perfil: Path) -> tuple[int, int]:
    """Deixa somente imagens, vídeos e dados_do_perfil.txt na pasta do perfil."""
    pasta_imagens = pasta_perfil / "imagens"
    pasta_videos = pasta_perfil / "videos"
    pasta_imagens.mkdir(parents=True, exist_ok=True)
    pasta_videos.mkdir(parents=True, exist_ok=True)
    for arquivo in list(pasta_perfil.rglob("*")):
        if not arquivo.is_file():
            continue
        if arquivo == pasta_perfil / "dados_do_perfil.txt":
            continue

        extensao = arquivo.suffix.lower()
        if extensao in EXTENSOES_DE_IMAGEM:
            pasta_destino = pasta_imagens
        elif extensao in EXTENSOES_DE_VIDEO:
            pasta_destino = pasta_videos
        elif extensao in {".json", ".xz", ".txt", ".part", ".tmp"} or arquivo.name == "id":
            arquivo.unlink()
            continue
        else:
            continue

        if arquivo.parent == pasta_destino:
            continue

        destino = _destino_sem_colisao(arquivo, pasta_destino)
        if destino.exists() and _arquivos_iguais(arquivo, destino):
            arquivo.unlink()
        else:
            arquivo.replace(destino)

    for pasta in sorted(
        (item for item in pasta_perfil.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        if pasta in {pasta_imagens, pasta_videos}:
            continue
        try:
            pasta.rmdir()
        except OSError:
            pass

    quantidade_imagens = sum(1 for item in pasta_imagens.iterdir() if item.is_file())
    quantidade_videos = sum(1 for item in pasta_videos.iterdir() if item.is_file())
    return quantidade_imagens, quantidade_videos


def salvar_dados_do_perfil(perfil: Any, pasta_perfil: Path) -> Path:
    perfil._obtain_metadata()
    node = dict(getattr(perfil, "_node", {}))
    endereco = node.get("business_address_json") or {}
    if isinstance(endereco, str):
        try:
            endereco = json.loads(endereco)
        except json.JSONDecodeError:
            endereco = {}
    if not isinstance(endereco, dict):
        endereco = {}

    cidade = node.get("city_name") or endereco.get("city_name") or endereco.get("city")
    estado = node.get("region_name") or endereco.get("region_name") or endereco.get("region")
    localidade = ", ".join(str(valor) for valor in (cidade, estado) if valor)
    rua = node.get("address_street") or endereco.get("street_address") or endereco.get("street")

    def exibir(valor: Any) -> str:
        return str(valor).strip() if valor not in (None, "") else "Não informado"

    def atributo(nome: str, padrao: Any = None) -> Any:
        try:
            return getattr(perfil, nome)
        except (AttributeError, KeyError):
            return padrao

    linhas = [
        "DADOS DO PERFIL",
        "",
        f"Usuário: @{atributo('username', 'desconhecido')}",
        f"Nome: {exibir(atributo('full_name'))}",
        f"Cidade: {exibir(localidade)}",
        f"Endereço público: {exibir(rua)}",
        f"Categoria: {exibir(node.get('business_category_name') or node.get('category'))}",
        f"Site: {exibir(atributo('external_url'))}",
        f"E-mail público: {exibir(node.get('public_email'))}",
        f"Telefone público: {exibir(node.get('public_phone_number'))}",
        f"Seguidores: {exibir(atributo('followers'))}",
        f"Seguindo: {exibir(atributo('followees'))}",
        f"Publicações: {exibir(atributo('mediacount'))}",
        f"Perfil privado: {'Sim' if atributo('is_private', False) else 'Não'}",
        f"Perfil verificado: {'Sim' if atributo('is_verified', False) else 'Não'}",
        "",
        "Biografia:",
        exibir(atributo('biography')),
        "",
    ]
    pasta_perfil.mkdir(parents=True, exist_ok=True)
    destino = pasta_perfil / "dados_do_perfil.txt"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    return destino


def opcoes_download_perfil(configuracao: Configuracao) -> dict[str, bool]:
    return {
        "profile_pic": True,
        "posts": True,
        "tagged": configuracao.completo,
        "igtv": configuracao.completo,
        "highlights": configuracao.completo,
        "stories": configuracao.completo,
        "fast_update": configuracao.atualizar,
        "raise_errors": True,
        # O endpoint dedicado de Reels costuma responder 401 sem uma sessão.
        "reels": configuracao.completo,
    }


def _conectar_logs(loader: Any, registrar: Registrador) -> None:
    contexto = loader.context

    def log(*mensagens: object, sep: str = "", end: str = "\n", flush: bool = False) -> None:
        del flush
        texto = sep.join(str(mensagem) for mensagem in mensagens)
        if end and texto:
            texto += end.rstrip("\n")
        if texto:
            registrar(texto)

    def error(mensagem: object, repeat_at_end: bool = True) -> None:
        texto = str(mensagem)
        registrar(f"ERRO: {texto}")
        if repeat_at_end:
            contexto.error_log.append(texto)

    contexto.log = log
    contexto.error = error


def _criar_loader(modulo: Any, configuracao: Configuracao, registrar: Registrador) -> Any:
    loader = modulo.Instaloader(**opcoes_instaloader(configuracao))
    _conectar_logs(loader, registrar)
    return loader


def _proteger_sessao(arquivo_de_sessao: Path) -> None:
    if not arquivo_de_sessao.exists():
        return
    try:
        os.chmod(arquivo_de_sessao, 0o600)
    except OSError:
        pass


def _autenticar(
    modulo: Any,
    loader: Any,
    configuracao: Configuracao,
    senha: str | None,
    obter_senha: Solicitador,
    obter_codigo_2fa: Solicitador,
    registrar: Registrador,
) -> Any:
    assert configuracao.login is not None
    usuario = configuracao.login
    PASTA_DE_SESSOES.mkdir(mode=0o700, parents=True, exist_ok=True)
    caminho_da_sessao = arquivo_de_sessao(usuario)

    if caminho_da_sessao.exists():
        try:
            loader.load_session_from_file(usuario, filename=str(caminho_da_sessao))
            usuario_da_sessao = loader.test_login()
            if usuario_da_sessao:
                registrar(f"Sessão de @{usuario_da_sessao} carregada com segurança.")
                return loader
            registrar("A sessão salva expirou; será necessário entrar novamente.")
        except modulo.exceptions.InstaloaderException as erro:
            registrar(f"Não foi possível reutilizar a sessão salva: {erro}")

        loader.close()
        loader = _criar_loader(modulo, configuracao, registrar)

    senha_atual = senha or obter_senha()
    if not senha_atual:
        raise modulo.exceptions.LoginException("informe a senha para fazer login")

    registrar(f"Entrando como @{usuario}...")
    try:
        loader.login(usuario, senha_atual)
    except modulo.exceptions.TwoFactorAuthRequiredException:
        codigo = obter_codigo_2fa().strip()
        if not codigo:
            raise modulo.exceptions.LoginException("código de autenticação não informado")
        loader.two_factor_login(codigo)

    loader.save_session_to_file(filename=str(caminho_da_sessao))
    _proteger_sessao(caminho_da_sessao)
    registrar("Login concluído; somente o cookie de sessão foi salvo.")
    return loader


def _autenticar_com_navegador(
    modulo: Any,
    loader: Any,
    navegador: str,
    registrar: Registrador,
) -> Any:
    if navegador == "brave":
        if _carregar_sessao_brave_salva(modulo, loader, registrar):
            return loader
        cookies_do_instagram = _abrir_login_brave(modulo, registrar)
    else:
        try:
            browser_cookie3 = importlib.import_module("browser_cookie3")
        except ImportError as erro:
            raise modulo.exceptions.LoginException(
                "instale browser-cookie3 para usar a sessão do navegador"
            ) from erro

        navegadores = {
            "chrome": browser_cookie3.chrome,
            "edge": browser_cookie3.edge,
            "firefox": browser_cookie3.firefox,
        }
        leitor = navegadores.get(navegador)
        if leitor is None:
            raise modulo.exceptions.LoginException("navegador não suportado")

        registrar(f"Lendo a sessão do Instagram no {navegador.title()}...")
        try:
            cookies_do_instagram = {
                cookie.name: cookie.value
                for cookie in leitor(domain_name="instagram.com")
                if "instagram" in cookie.domain.lower()
            }
        except Exception as erro:
            raise modulo.exceptions.LoginException(
                f"não foi possível ler os cookies do {navegador.title()}; "
                "feche o navegador e tente novamente"
            ) from erro

    if not cookies_do_instagram:
        raise modulo.exceptions.LoginException(
            f"nenhuma sessão do Instagram foi encontrada no {navegador.title()}; "
            "entre em instagram.com nesse navegador primeiro"
        )

    loader.context.update_cookies(cookies_do_instagram)
    usuario = loader.test_login()
    if not usuario:
        raise modulo.exceptions.LoginException(
            f"a sessão do Instagram no {navegador.title()} não está válida"
        )

    loader.context.username = usuario
    PASTA_DE_SESSOES.mkdir(mode=0o700, parents=True, exist_ok=True)
    caminho_da_sessao = arquivo_de_sessao(usuario)
    loader.save_session_to_file(filename=str(caminho_da_sessao))
    _proteger_sessao(caminho_da_sessao)
    if navegador == "brave":
        loader.save_session_to_file(filename=str(ARQUIVO_SESSAO_BRAVE))
        _proteger_sessao(ARQUIVO_SESSAO_BRAVE)
    registrar(f"Sessão de @{usuario} importada do {navegador.title()} com sucesso.")
    return loader


def _carregar_sessao_brave_salva(
    modulo: Any,
    loader: Any,
    registrar: Registrador,
) -> bool:
    if ARQUIVO_SESSAO_BRAVE.exists():
        candidato = ARQUIVO_SESSAO_BRAVE
    elif PASTA_DE_SESSOES.exists():
        sessoes = [
            caminho
            for caminho in PASTA_DE_SESSOES.glob("*.session")
            if caminho != ARQUIVO_SESSAO_BRAVE
        ]
        if len(sessoes) != 1:
            return False
        candidato = sessoes[0]
    else:
        return False

    registrar("Verificando a sessão do Brave salva anteriormente...")
    try:
        loader.load_session_from_file("brave", filename=str(candidato))
        usuario = loader.test_login()
    except modulo.exceptions.InstaloaderException as erro:
        registrar(f"A sessão salva não pôde ser reutilizada: {erro}")
        return False

    if not usuario:
        registrar("A sessão salva expirou; será necessário entrar novamente.")
        return False

    loader.context.username = usuario
    if candidato != ARQUIVO_SESSAO_BRAVE:
        loader.save_session_to_file(filename=str(ARQUIVO_SESSAO_BRAVE))
        _proteger_sessao(ARQUIVO_SESSAO_BRAVE)
    registrar(f"Sessão de @{usuario} reutilizada com sucesso.")
    return True


def _localizar_brave() -> Path | None:
    candidatos: list[Path] = []
    for variavel in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        raiz = os.environ.get(variavel)
        if raiz:
            candidatos.append(
                Path(raiz) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
            )
    return next((caminho for caminho in candidatos if caminho.exists()), None)


def _porta_local_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.bind(("127.0.0.1", 0))
        return int(servidor.getsockname()[1])


def _aguardar_websocket_brave(processo: Any, porta: int, segundos: int = 30) -> str:
    limite = time.monotonic() + segundos
    url = f"http://127.0.0.1:{porta}/json/version"
    while time.monotonic() < limite:
        if processo.poll() is not None:
            raise RuntimeError("o Brave fechou durante a inicialização")
        try:
            with urlopen(url, timeout=1) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            websocket_url = dados.get("webSocketDebuggerUrl")
            if websocket_url:
                return str(websocket_url)
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    raise TimeoutError("o Brave não concluiu a inicialização em 30 segundos")


def _executar_comando_cdp(
    conexao: Any,
    identificador: int,
    metodo: str,
) -> dict[str, Any]:
    conexao.send(json.dumps({"id": identificador, "method": metodo, "params": {}}))
    while True:
        mensagem = json.loads(conexao.recv())
        if mensagem.get("id") != identificador:
            continue
        if "error" in mensagem:
            detalhe = mensagem["error"].get("message", "erro desconhecido")
            raise RuntimeError(f"CDP: {detalhe}")
        return dict(mensagem.get("result", {}))


def _encerrar_brave_isolado(processo: Any, conexao: Any | None) -> None:
    if conexao is not None:
        try:
            conexao.send(json.dumps({"id": 999999, "method": "Browser.close", "params": {}}))
        except Exception:
            pass
        try:
            conexao.close()
        except Exception:
            pass

    if processo is None or processo.poll() is not None:
        return
    try:
        processo.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        subprocess.run(
            ["taskkill", "/PID", str(processo.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        processo.terminate()


def _abrir_login_brave(
    modulo: Any,
    registrar: Registrador,
) -> dict[str, str]:
    caminho_brave = _localizar_brave()
    if caminho_brave is None:
        raise modulo.exceptions.LoginException("Brave não foi encontrado neste computador")

    try:
        websocket = importlib.import_module("websocket")
    except ImportError as erro:
        raise modulo.exceptions.LoginException(
            "instale websocket-client para usar o login seguro do Brave"
        ) from erro

    pasta_temporaria = Path(tempfile.mkdtemp(prefix="ig_brave_"))
    porta = _porta_local_livre()
    processo = None
    conexao = None
    registrar("Abrindo uma janela isolada do Brave para o Instagram...")
    try:
        processo = subprocess.Popen(
            [
                str(caminho_brave),
                f"--user-data-dir={pasta_temporaria}",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={porta}",
                "--new-window",
                "--disable-background-mode",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.instagram.com/accounts/login/",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        websocket_url = _aguardar_websocket_brave(processo, porta)
        conexao = websocket.create_connection(
            websocket_url,
            timeout=3,
            suppress_origin=True,
        )
        registrar(
            "Faça login nessa janela. Ela será fechada automaticamente quando "
            "a sessão for reconhecida."
        )

        limite = time.monotonic() + 600
        identificador = 1
        while time.monotonic() < limite:
            if processo.poll() is not None:
                raise RuntimeError("a janela foi fechada antes de concluir o login")
            resultado = _executar_comando_cdp(
                conexao,
                identificador,
                "Storage.getCookies",
            )
            identificador += 1
            cookies_do_instagram = {
                str(cookie["name"]): str(cookie["value"])
                for cookie in resultado.get("cookies", [])
                if "instagram" in str(cookie.get("domain", "")).lower()
            }
            if cookies_do_instagram.get("sessionid"):
                registrar("Login reconhecido; fechando somente a janela isolada do Brave...")
                return cookies_do_instagram
            time.sleep(1)

        raise TimeoutError("tempo esgotado aguardando o login no Brave")
    except modulo.exceptions.InstaloaderException:
        raise
    except Exception as erro:
        raise modulo.exceptions.LoginException(
            f"não foi possível obter a sessão pela janela isolada do Brave: {erro}"
        ) from erro
    finally:
        _encerrar_brave_isolado(processo, conexao)
        shutil.rmtree(pasta_temporaria, ignore_errors=True)


def obter_perfil_compativel(
    modulo: Any,
    contexto: Any,
    nome_do_perfil: str,
    registrar: Registrador,
) -> Any:
    """Contorna a remoção recente de um schema usado por web_profile_info."""
    def buscar_exato() -> Any:
        resultados = modulo.TopSearchResults(contexto, nome_do_perfil)
        for perfil_encontrado in resultados.get_profiles():
            if perfil_encontrado.username.lower() == nome_do_perfil.lower():
                return perfil_encontrado
        raise modulo.exceptions.ProfileNotExistsException(
            f"Perfil @{nome_do_perfil} não foi encontrado pela rota alternativa."
        )

    # Com login, a rota de busca seguida pela consulta por ID evita o schema
    # removido do endpoint web_profile_info.
    if contexto.is_logged_in:
        registrar("Localizando o perfil pela rota compatível do Instagram...")
        return buscar_exato()

    try:
        return modulo.Profile.from_username(contexto, nome_do_perfil)
    except modulo.exceptions.InstaloaderException as erro:
        if "ig_business_category_subvertical" not in str(erro):
            raise

    registrar(
        "O Instagram removeu um campo usado pela consulta padrão; "
        "tentando a rota compatível..."
    )
    return buscar_exato()


def executar(
    configuracao: Configuracao,
    *,
    senha: str | None = None,
    obter_senha: Solicitador | None = None,
    obter_codigo_2fa: Solicitador | None = None,
    ao_checkpoint: ManipuladorDeCheckpoint | None = None,
    registrar: Registrador = print,
) -> int:
    """Executa o download; a senha recebida é usada somente em memória."""
    tem_autenticacao = bool(configuracao.login or configuracao.navegador)
    if configuracao.completo and not tem_autenticacao:
        registrar("ERRO: conteúdo completo exige login ou sessão do navegador.")
        return 2

    if importlib.util.find_spec("instaloader") is None:
        registrar(
            "ERRO: Instaloader não está instalado. Execute "
            "python -m pip install -r requirements.txt"
        )
        return 2

    modulo = importlib.import_module("instaloader")
    configuracao.saida.mkdir(parents=True, exist_ok=True)
    loader: Any | None = None

    try:
        loader = _criar_loader(modulo, configuracao, registrar)
        if configuracao.navegador:
            loader = _autenticar_com_navegador(
                modulo,
                loader,
                configuracao.navegador,
                registrar,
            )
        elif configuracao.login:
            loader = _autenticar(
                modulo,
                loader,
                configuracao,
                senha,
                obter_senha or (lambda: getpass.getpass("Senha do Instagram: ")),
                obter_codigo_2fa or (lambda: input("Código de autenticação em dois fatores: ")),
                registrar,
            )

        registrar(f"Destino: {configuracao.saida}")
        registrar(f"Perfis: {', '.join(configuracao.perfis)}")
        if not tem_autenticacao:
            registrar(
                "Modo público: baixando publicações visíveis. Para Reels dedicados, "
                "stories e destaques, ative o login e o conteúdo completo."
            )

        for nome_do_perfil in configuracao.perfis:
            registrar(f"Preparando @{nome_do_perfil}...")
            perfil = obter_perfil_compativel(
                modulo,
                loader.context,
                nome_do_perfil,
                registrar,
            )
            pasta_perfil = configuracao.saida / perfil.username
            salvar_dados_do_perfil(perfil, pasta_perfil)
            try:
                loader.download_profiles({perfil}, **opcoes_download_perfil(configuracao))
            finally:
                imagens, videos = organizar_pasta_do_perfil(pasta_perfil)
                registrar(
                    f"Pasta organizada: {imagens} imagem(ns), {videos} vídeo(s) "
                    "e dados_do_perfil.txt."
                )

        if loader.context.has_stored_errors:
            registrar("O download terminou com avisos ou erros; confira as mensagens acima.")
            return 1

        registrar("Download concluído.")
        return 0
    except KeyboardInterrupt:
        registrar("Download interrompido; o progresso foi preservado.")
        return 130
    except modulo.exceptions.LoginException as erro:
        url_checkpoint = extrair_url_checkpoint(str(erro))
        if url_checkpoint:
            registrar(
                "ERRO: o Instagram exige uma confirmação de segurança no navegador."
            )
            if ao_checkpoint:
                ao_checkpoint(url_checkpoint)
            else:
                registrar(f"Abra, confirme o login e tente novamente: {url_checkpoint}")
            return 3
        registrar(f"ERRO de login: {erro}")
        return 1
    except (modulo.exceptions.InstaloaderException, OSError) as erro:
        registrar(f"ERRO: {erro}")
        registrar("Não repita tentativas rapidamente se o Instagram estiver limitando o acesso.")
        return 1
    except Exception as erro:  # evita que a interface encerre sem explicar o motivo
        registrar(f"ERRO inesperado: {erro}")
        return 1
    finally:
        if loader is not None:
            loader.close()


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Baixa o conteúdo de perfis do Instagram e separa somente em "
            "imagens, vídeos e dados do perfil."
        )
    )
    parser.add_argument(
        "perfis",
        nargs="+",
        type=normalizar_perfil,
        help="um ou mais perfis: usuario, @usuario ou URL do perfil",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=PASTA_DO_PROJETO / "downloads",
        help="pasta de destino (padrão: ./downloads)",
    )
    parser.add_argument(
        "--login",
        type=normalizar_login,
        help="seu usuário ou e-mail do Instagram; a senha será solicitada de forma oculta",
    )
    parser.add_argument(
        "--navegador",
        choices=("brave", "chrome", "edge", "firefox"),
        help="reutiliza uma sessão já aberta no navegador em vez de pedir senha",
    )
    parser.add_argument(
        "--completo",
        action="store_true",
        help="inclui Reels, stories atuais, destaques, marcados e IGTV; exige --login",
    )
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="para ao encontrar conteúdo já baixado, tornando atualizações mais rápidas",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = criar_parser()
    args = parser.parse_args(argv)

    if args.login and args.navegador:
        parser.error("use apenas --login ou --navegador")
    if args.completo and not (args.login or args.navegador):
        parser.error("--completo exige --login ou --navegador")
    configuracao = Configuracao(
        perfis=remover_duplicados(args.perfis),
        saida=args.saida.expanduser().resolve(),
        login=args.login,
        navegador=args.navegador,
        completo=args.completo,
        atualizar=args.atualizar,
    )
    return executar(configuracao)


if __name__ == "__main__":
    raise SystemExit(main())
