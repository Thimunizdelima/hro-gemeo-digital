import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import uvicorn

from app import app
from database import init_db
from simulation_engine import atualizar_atrasos_e_rupturas_prescricao


def porta_em_uso(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def servidor_hro_ativo(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dashboard", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def abrir_navegador(url: str):
    try:
        subprocess.run(["open", "-a", "Safari", url], check=False)
    except Exception:
        webbrowser.open(url)


def iniciar_servidor_background(port: int):
    init_db(force_reset=False)
    atualizar_atrasos_e_rupturas_prescricao()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def main():
    port = 8090
    if porta_em_uso(port) and not servidor_hro_ativo(port):
        port = 8091

    url = f"http://127.0.0.1:{port}"

    if not servidor_hro_ativo(port):
        t = threading.Thread(target=iniciar_servidor_background, args=(port,), daemon=True)
        t.start()
        for _ in range(30):
            if servidor_hro_ativo(port):
                break
            time.sleep(0.2)

    abrir_navegador(url)

    # Se estiver rodando via duplo-clique no macOS (.app sem terminal anexado), exibe controle nativo
    if not sys.stdin or not sys.stdin.isatty():
        while True:
            script = (
                f'display dialog "🏥 HRO Gêmeo Digital & Prescrição Eletrônica está em execução!\\n\\n'
                f'Endereço local: {url}\\n\\n'
                f'Você pode usar o simulador normalmente no Safari." '
                f'with title "HRO Gêmeo Digital — Simulador Ativo" '
                f'buttons {{"Encerrar Simulador", "Abrir no Safari"}} default button "Abrir no Safari"'
            )
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if "Abrir no Safari" in res.stdout:
                abrir_navegador(url)
            else:
                break
    else:
        print(f"============================================================")
        print(f"🏥 HRO Gêmeo Digital ativo em: {url}")
        print(f"Pressione Ctrl+C para encerrar o simulador.")
        print(f"============================================================")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nEncerrando HRO Gêmeo Digital...")


if __name__ == "__main__":
    main()
