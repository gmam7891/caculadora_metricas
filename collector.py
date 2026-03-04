import time
import argparse
import logging
import os
from twitch_client import TwitchClient
from storage import connect, init_db, save_live_sample
from dotenv import load_dotenv

# ===================== CONFIGURAÇÃO DE LOG =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()

VIRTUAL_CASINO_GAME_ID = "29452"


def load_streamers_file(path: str):
    if not os.path.exists(path):
        logger.warning(f"Arquivo {path} não encontrado!")
        return []
    seen = set()
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip().lower()
            if s and not s.startswith("#") and s not in seen:
                seen.add(s)
                result.append(s)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels-file", default="streamers.txt")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    db_path = os.getenv("APP_DB_PATH", "./data/app.db")

    if not client_id or not client_secret:
        logger.error("TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET não encontrados no .env")
        return

    tc = None
    conn = None

    logger.info("🚀 Coletor de Virtual Casino iniciado")
    logger.info(f"Intervalo: {args.interval}s | Arquivo: {args.channels_file}")

    while True:
        try:
            # --- Reconexão automática do TwitchClient (token nunca expira) ---
            if tc is None:
                logger.info("🔑 Criando/renovando token da Twitch...")
                tc = TwitchClient(client_id, client_secret)

            # --- Reconexão automática do banco ---
            if conn is None:
                logger.info("🗄️ Conectando ao banco de dados...")
                conn = connect(db_path)
                init_db(conn)

            channels = load_streamers_file(args.channels_file)
            if not channels:
                logger.warning("Nenhum canal carregado. Verifique streamers.txt")
                time.sleep(args.interval)
                continue

            logger.info(f"Verificando {len(channels)} canais...")

            try:
                live_streams = tc.get_streams_by_logins(channels)
            except Exception as e:
                logger.warning(f"Erro na API Twitch (renovando token): {e}")
                tc = None  # Força renovação na próxima iteração
                time.sleep(30)
                continue

            saved_count = 0
            skipped_count = 0

            for login, stream in live_streams.items():
                try:
                    viewer_count = int(stream.get("viewer_count", 0))
                    game_id = stream.get("game_id")
                    game_name = stream.get("game_name", "Desconhecido")

                    if game_id != VIRTUAL_CASINO_GAME_ID:
                        logger.info(f"⏭️  {login} ignorado ({game_name})")
                        skipped_count += 1
                        continue

                    save_live_sample(
                        conn=conn,
                        channel=login,
                        viewers=viewer_count,
                        game_id=game_id,
                        game_name=game_name
                    )
                    saved_count += 1
                    logger.info(f"✅ {login} | {viewer_count:,} viewers | Virtual Casino")

                except Exception as e:
                    logger.error(f"Erro ao processar {login}: {e}")

            logger.info(f"Rodada finalizada → Salvos: {saved_count} | Ignorados: {skipped_count}")

        except Exception as e:
            logger.error(f"Erro geral no loop: {e}")
            # Reset conexões para forçar reconexão
            tc = None
            conn = None
            time.sleep(30)
            continue

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
