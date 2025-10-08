import json
import time

import requests
import yaml
from box.box_list import BoxList
from loguru import logger
from typing import Dict, Optional
from box import Box, BoxList, BoxError
from pathlib import Path
from requests import request

from utils.decorator import retry

"""Открываем и читаем YAML файл"""
def load_config() -> Optional[Dict]:
    try:
        with open('setting.yaml', 'r') as file:
            config = yaml.safe_load(file)
            return Box(config)
    except yaml.YAMLError as e:
        logger.error(f"Ошибка разбора YAML: {e}")
    except FileNotFoundError:
        logger.error(f"Файл конфигурации не найден")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке конфига: {e}")
    return None

def open_private_key():
    file = 'private_keys.txt'
    try:
        with open(file, 'r', encoding='utf-8') as file:
            private_keys = [line.strip() for line in file if line.strip()]

        if not private_keys:
            logger.error(f"Файл {file.name} пуст. Добавьте приватные ключи.")
            return None

        return BoxList(private_keys)

    except FileNotFoundError:
        logger.error(f"Файл {file} не найден. Пожалуйста, создайте его и добавьте приватные ключи.")
        return None


@retry(max_attempts=3, delay=1)
def make_request(method="GET", url=None, **kwargs):
    response = requests.request(method=method, url=url, **kwargs)
    response.raise_for_status()
    return response


def load_or_fetch_chainlist_data(cache_duration_seconds: int = 86400) -> Optional[Box]:
    """
    Загружает данные с Chainlist из локального кэша или скачивает их, если кэш устарел.
    :param cache_duration_seconds: Время жизни кэша в секундах (по умолчанию 24 часа).
    :return: Объект Box с данными или None в случае ошибки.
    """
    full_path = Path('utils/chain_list.json')
    url = "https://chainlist.org/rpcs.json"

    # Проверяем, нужно ли обновлять кэш
    should_download = True
    if full_path.exists():
        file_mod_time = full_path.stat().st_mtime
        if (time.time() - file_mod_time) < cache_duration_seconds:
            logger.info("Используем локальный кэш Chainlist (файл свежий).")
            should_download = False
        else:
            logger.info("Локальный кэш Chainlist устарел. Скачиваем свежую версию...")

    if should_download:
        try:
            logger.info("Загружаем актуальный список сетей с Chainlist.org...")
            chainlist_data = make_request(method="GET", url=url, timeout=20).json()

            # ИСПРАВЛЕНИЕ: Создаем Box из словаря
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(chainlist_data, f, indent=2, ensure_ascii=False)

            logger.success(f"Кэш Chainlist успешно сохранен в {full_path}")
        except Exception as e:
            logger.error(f"Не удалось скачать или сохранить данные с Chainlist: {e}")
            # Если скачать не удалось, но старый файл есть, попробуем использовать его
            if not full_path.exists():
                return None

    # Загружаем данные из файла
    try:
        # ИСПРАВЛЕНИЕ: Используем .from_file()
        logger.info(f"Загружаем данные из файла {full_path}")
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Файл кэша {full_path} поврежден или не найден: {e}")
        full_path.unlink(missing_ok=True)  # Удаляем битый файл
        return None

config = load_config()
private_keys = open_private_key()
chains_list = BoxList(load_or_fetch_chainlist_data())
