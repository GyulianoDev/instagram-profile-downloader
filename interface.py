from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from baixar_perfil import (
    PASTA_DO_PROJETO,
    Configuracao,
    arquivo_de_sessao,
    executar,
    normalizar_login,
    normalizar_perfil,
)


class InterfaceDownloader:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.fila: queue.Queue[tuple[str, object]] = queue.Queue()
        self.baixando = False

        self.perfil = tk.StringVar()
        self.saida = tk.StringVar(value=str(PASTA_DO_PROJETO / "downloads"))
        self.usar_login = tk.BooleanVar(value=False)
        self.usar_navegador = tk.BooleanVar(value=False)
        self.navegador = tk.StringVar(value="Brave")
        self.usuario = tk.StringVar()
        self.senha = tk.StringVar()
        self.mostrar_senha = tk.BooleanVar(value=False)
        self.completo = tk.BooleanVar(value=False)
        self.atualizar = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Pronto para baixar")
        self.aviso_sessao = tk.StringVar(value="")
        self.ultimo_erro = ""
        self.checkpoint_exibido = False

        self._configurar_janela()
        self._montar_tela()
        self._alternar_login(selecionar_completo=False)
        self.root.after(100, self._processar_fila)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar)

    def _configurar_janela(self) -> None:
        self.root.title("Baixar perfil do Instagram")
        self.root.geometry("760x760")
        self.root.minsize(640, 620)
        self.root.configure(background="#f4f5f7")

        estilo = ttk.Style(self.root)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure("Tela.TFrame", background="#f4f5f7")
        estilo.configure(
            "Titulo.TLabel",
            background="#f4f5f7",
            foreground="#171717",
            font=("Segoe UI", 20, "bold"),
        )
        estilo.configure(
            "Subtitulo.TLabel",
            background="#f4f5f7",
            foreground="#565b65",
            font=("Segoe UI", 10),
        )
        estilo.configure("Card.TLabelframe", background="#ffffff", borderwidth=1)
        estilo.configure(
            "Card.TLabelframe.Label",
            background="#ffffff",
            foreground="#252525",
            font=("Segoe UI", 10, "bold"),
        )
        estilo.configure("Card.TFrame", background="#ffffff")
        estilo.configure("Card.TLabel", background="#ffffff", foreground="#252525")
        estilo.configure("Dica.TLabel", background="#ffffff", foreground="#68707c")
        estilo.configure("Acao.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 10))

    def _montar_tela(self) -> None:
        principal = ttk.Frame(self.root, padding=24, style="Tela.TFrame")
        principal.pack(fill="both", expand=True)
        principal.columnconfigure(0, weight=1)
        principal.rowconfigure(4, weight=1)

        ttk.Label(principal, text="Instagram Profile Downloader", style="Titulo.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            principal,
            text="Escolha um perfil, entre na sua conta se necessário e acompanhe o download.",
            style="Subtitulo.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 18))

        destino = ttk.LabelFrame(
            principal, text="Perfil e destino", padding=16, style="Card.TLabelframe"
        )
        destino.grid(row=2, column=0, sticky="ew")
        destino.columnconfigure(0, weight=1)

        ttk.Label(destino, text="Perfil para baixar", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.campo_perfil = ttk.Entry(destino, textvariable=self.perfil, font=("Segoe UI", 11))
        self.campo_perfil.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 12))
        ttk.Label(
            destino,
            text="Aceita nome, @nome ou URL completa do perfil.",
            style="Dica.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 12))

        ttk.Label(destino, text="Salvar em", style="Card.TLabel").grid(
            row=3, column=0, sticky="w"
        )
        self.campo_saida = ttk.Entry(destino, textvariable=self.saida)
        self.campo_saida.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        self.botao_escolher_pasta = ttk.Button(
            destino, text="Escolher pasta", command=self._escolher_pasta
        )
        self.botao_escolher_pasta.grid(row=4, column=1, padx=(8, 0), pady=(5, 0))

        login = ttk.LabelFrame(
            principal, text="Login e opções", padding=16, style="Card.TLabelframe"
        )
        login.grid(row=3, column=0, sticky="ew", pady=(14, 14))
        login.columnconfigure(1, weight=1)

        self.check_usar_login = ttk.Checkbutton(
            login,
            text="Usar login (necessário para perfis privados, stories e destaques)",
            variable=self.usar_login,
            command=self._alternar_login,
        )
        self.check_usar_login.grid(row=0, column=0, columnspan=3, sticky="w")

        self.check_usar_navegador = ttk.Checkbutton(
            login,
            text="Entrar usando o navegador (recomendado)",
            variable=self.usar_navegador,
            command=self._alternar_metodo_login,
        )
        self.check_usar_navegador.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(login, text="Navegador", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.combo_navegador = ttk.Combobox(
            login,
            textvariable=self.navegador,
            values=("Brave", "Chrome", "Edge", "Firefox"),
            state="readonly",
            width=16,
        )
        self.combo_navegador.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

        ttk.Label(login, text="Usuário ou e-mail", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        self.campo_usuario = ttk.Entry(login, textvariable=self.usuario)
        self.campo_usuario.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))
        self.campo_usuario.bind("<FocusOut>", lambda _evento: self._verificar_sessao())

        ttk.Label(login, text="Senha", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        self.campo_senha = ttk.Entry(login, textvariable=self.senha, show="*")
        self.campo_senha.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))
        self.botao_mostrar = ttk.Checkbutton(
            login,
            text="Mostrar",
            variable=self.mostrar_senha,
            command=self._alternar_visibilidade_senha,
        )
        self.botao_mostrar.grid(row=4, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(login, textvariable=self.aviso_sessao, style="Dica.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 4)
        )

        self.check_completo = ttk.Checkbutton(
            login,
            text="Baixar também Reels, stories atuais, destaques, marcados e IGTV",
            variable=self.completo,
        )
        self.check_completo.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.check_atualizar = ttk.Checkbutton(
            login,
            text="Atualização rápida (parar ao encontrar conteúdo já baixado)",
            variable=self.atualizar,
        )
        self.check_atualizar.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        progresso = ttk.LabelFrame(
            principal, text="Progresso", padding=12, style="Card.TLabelframe"
        )
        progresso.grid(row=4, column=0, sticky="nsew")
        progresso.columnconfigure(0, weight=1)
        progresso.rowconfigure(2, weight=1)

        ttk.Label(progresso, textvariable=self.status, style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.barra = ttk.Progressbar(progresso, mode="indeterminate")
        self.barra.grid(row=1, column=0, sticky="ew", pady=(7, 10))

        self.log = tk.Text(
            progresso,
            height=9,
            wrap="word",
            state="disabled",
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#ffffff",
            relief="flat",
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        self.log.grid(row=2, column=0, sticky="nsew")

        self.botao_baixar = ttk.Button(
            principal,
            text="Baixar perfil",
            command=self._iniciar_download,
            style="Acao.TButton",
        )
        self.botao_baixar.grid(row=5, column=0, sticky="ew", pady=(14, 0))

        self.campo_perfil.focus_set()

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(
            parent=self.root,
            title="Escolha onde salvar os perfis",
            initialdir=self.saida.get() or str(PASTA_DO_PROJETO),
        )
        if pasta:
            self.saida.set(pasta)

    def _alternar_login(self, selecionar_completo: bool = True) -> None:
        habilitado = self.usar_login.get()
        self.check_usar_navegador.configure(state="normal" if habilitado else "disabled")
        self.check_completo.configure(state="normal" if habilitado else "disabled")

        if habilitado:
            if selecionar_completo:
                self.completo.set(True)
        else:
            self.usar_navegador.set(False)
            self.senha.set("")
            self.completo.set(False)
            self.aviso_sessao.set("")
        self._alternar_metodo_login()

    def _alternar_metodo_login(self) -> None:
        habilitado = self.usar_login.get()
        pelo_navegador = habilitado and self.usar_navegador.get()
        estado_credenciais = "disabled" if pelo_navegador or not habilitado else "normal"
        self.campo_usuario.configure(state=estado_credenciais)
        self.campo_senha.configure(state=estado_credenciais)
        self.botao_mostrar.configure(state=estado_credenciais)
        self.combo_navegador.configure(state="readonly" if pelo_navegador else "disabled")

        if pelo_navegador:
            self.senha.set("")
            if self.navegador.get().lower() == "brave":
                self.aviso_sessao.set(
                    "Será aberta uma janela isolada; o Brave que você já usa pode continuar aberto."
                )
            else:
                self.aviso_sessao.set(
                    "Entre em instagram.com nesse navegador antes de iniciar o download."
                )
        elif habilitado:
            self._verificar_sessao()
            self.campo_usuario.focus_set()

    def _alternar_visibilidade_senha(self) -> None:
        self.campo_senha.configure(show="" if self.mostrar_senha.get() else "*")

    def _verificar_sessao(self) -> None:
        if not self.usar_login.get() or self.usar_navegador.get():
            return
        try:
            usuario = normalizar_login(self.usuario.get())
        except argparse.ArgumentTypeError:
            self.aviso_sessao.set("")
            return

        arquivo = arquivo_de_sessao(usuario)
        if arquivo.exists():
            self.aviso_sessao.set("Sessão salva encontrada; a senha pode ficar vazia.")
        else:
            self.aviso_sessao.set("Primeiro login: informe a senha; ela não será salva.")

    def _iniciar_download(self) -> None:
        try:
            perfil = normalizar_perfil(self.perfil.get())
        except argparse.ArgumentTypeError as erro:
            messagebox.showerror("Perfil inválido", str(erro), parent=self.root)
            self.campo_perfil.focus_set()
            return

        texto_saida = self.saida.get().strip()
        if not texto_saida:
            messagebox.showerror("Pasta obrigatória", "Escolha uma pasta de destino.", parent=self.root)
            return

        login: str | None = None
        navegador: str | None = None
        if self.usar_login.get():
            if self.usar_navegador.get():
                navegador = self.navegador.get().lower()
            else:
                try:
                    login = normalizar_login(self.usuario.get())
                except argparse.ArgumentTypeError as erro:
                    messagebox.showerror("Login inválido", str(erro), parent=self.root)
                    self.campo_usuario.focus_set()
                    return

                arquivo = arquivo_de_sessao(login)
                if not arquivo.exists() and not self.senha.get():
                    messagebox.showerror(
                        "Senha obrigatória",
                        "Informe a senha no primeiro login. Ela será usada somente em memória.",
                        parent=self.root,
                    )
                    self.campo_senha.focus_set()
                    return

        configuracao = Configuracao(
            perfis=(perfil,),
            saida=Path(texto_saida).expanduser().resolve(),
            login=login,
            navegador=navegador,
            completo=self.completo.get(),
            atualizar=self.atualizar.get(),
        )
        senha = self.senha.get() if login else None
        self.senha.set("")
        self._limpar_log()
        self.ultimo_erro = ""
        self.checkpoint_exibido = False
        self._definir_ocupado(True)
        self._registrar("Iniciando download...")

        threading.Thread(
            target=self._executar_em_background,
            args=(configuracao, senha),
            daemon=True,
            name="download-instagram",
        ).start()

    def _executar_em_background(self, configuracao: Configuracao, senha: str | None) -> None:
        codigo = executar(
            configuracao,
            senha=senha,
            obter_senha=lambda: "",
            obter_codigo_2fa=self._pedir_codigo_2fa,
            ao_checkpoint=lambda url: self.fila.put(("checkpoint", url)),
            registrar=self._registrar,
        )
        senha = None
        self.fila.put(("concluido", codigo))

    def _pedir_codigo_2fa(self) -> str:
        evento = threading.Event()
        resposta: list[str] = []

        def perguntar() -> None:
            codigo = simpledialog.askstring(
                "Autenticação em dois fatores",
                "Digite o código enviado pelo Instagram:",
                parent=self.root,
            )
            resposta.append(codigo or "")
            evento.set()

        self.root.after(0, perguntar)
        evento.wait()
        return resposta[0]

    def _registrar(self, mensagem: str) -> None:
        self.fila.put(("log", mensagem))

    def _processar_fila(self) -> None:
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "log":
                    mensagem = str(valor)
                    self._adicionar_log(mensagem)
                    self.status.set(mensagem.splitlines()[-1][:90])
                    if any(
                        marcador in mensagem.lower()
                        for marcador in ("erro:", "unauthorized", "login required", "não foi possível")
                    ):
                        self.ultimo_erro = mensagem.splitlines()[-1]
                elif tipo == "concluido":
                    self._finalizar_download(int(valor))
                elif tipo == "checkpoint":
                    self._mostrar_checkpoint(str(valor))
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._processar_fila)

    def _adicionar_log(self, mensagem: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", mensagem.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _mostrar_checkpoint(self, url: str) -> None:
        self.checkpoint_exibido = True
        abrir = messagebox.askyesno(
            "Confirmação exigida pelo Instagram",
            "O Instagram bloqueou o login até você confirmar que foi você.\n\n"
            "Deseja abrir a página oficial de confirmação no navegador?\n\n"
            "Se abrir somente a página inicial, entre na sua conta e use a opção "
            "'sessão já aberta no navegador' no aplicativo.",
            parent=self.root,
        )
        if abrir:
            webbrowser.open(url, new=2)

    def _limpar_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _definir_ocupado(self, ocupado: bool) -> None:
        self.baixando = ocupado
        self.botao_baixar.configure(state="disabled" if ocupado else "normal")
        self.campo_perfil.configure(state="disabled" if ocupado else "normal")
        self.campo_saida.configure(state="disabled" if ocupado else "normal")
        self.botao_escolher_pasta.configure(state="disabled" if ocupado else "normal")
        self.check_usar_login.configure(state="disabled" if ocupado else "normal")
        self.check_atualizar.configure(state="disabled" if ocupado else "normal")
        if ocupado:
            for controle in (
                self.campo_usuario,
                self.campo_senha,
                self.botao_mostrar,
                self.check_usar_navegador,
                self.combo_navegador,
                self.check_completo,
            ):
                controle.configure(state="disabled")
            self.status.set("Baixando...")
            self.barra.start(12)
        else:
            self.barra.stop()
            self._alternar_login(selecionar_completo=False)

    def _finalizar_download(self, codigo: int) -> None:
        self._definir_ocupado(False)
        if codigo == 0:
            self.status.set("Download concluído")
            messagebox.showinfo(
                "Concluído",
                f"Arquivos salvos em:\n{self.saida.get()}",
                parent=self.root,
            )
        elif codigo == 3:
            self.status.set("Confirme o login no navegador e tente novamente")
            if not self.checkpoint_exibido:
                messagebox.showwarning(
                    "Confirmação necessária",
                    "Confirme o acesso no Instagram e tente o download novamente.",
                    parent=self.root,
                )
        else:
            self.status.set("Download não concluído")
            detalhe = self.ultimo_erro or "Confira as mensagens na área de progresso."
            messagebox.showerror(
                "Não foi possível concluir",
                f"{detalhe}\n\nConfira também as mensagens na área de progresso.",
                parent=self.root,
            )

    def _fechar(self) -> None:
        if self.baixando and not messagebox.askyesno(
            "Interromper download?",
            "Há um download em andamento. Fechar a janela interromperá o processo.",
            parent=self.root,
        ):
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    InterfaceDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
