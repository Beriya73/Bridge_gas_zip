from loguru import logger
from box import Box, BoxList
from utils.config import config
from typing import Optional, Tuple
from utils.decorator import retry
import requests

def check_load_configuration(config, private_keys, chains_list):
    if config is None or private_keys is None or chains_list is None:
        if config is None:
            logger.error("Файл setting.yaml пуст")
        if private_keys is None:
            logger.error("Файл private_keys.txt пуст")
        if chains_list is None:
            logger.error("Файл chain_list.json пуст")
        return False
    return True

def search_two_chain(data: Box) -> Tuple[Optional[Box], Optional[Box]]:
    """
    Поиск входной и выходной сети согласно данным INPUT_CHAIN
    OUTPUT_CHAIN
    из config.yaml
    :param data:
    :return:
    """
    # Обрабатываем успешный ответ
    input_chain = None
    output_chain = None
    for chain in data.chains:
        if config.INPUT_CHAIN == chain.name:
            input_chain = Box(chain)
        elif config.OUTPUT_CHAIN == chain.name:
            output_chain = Box(chain)
        if input_chain and output_chain:
            break

    if input_chain is None or output_chain is None:
        if not input_chain:
            print(f"Неправильное название входной сети {config.INPUT_CHAIN}")
        if not output_chain:
            print(f"Неправильное название выходной сети {config.OUTPUT_CHAIN}")
        # Выводим на печать названия всех сетей
        chains_list =  sorted(data.chains, key=lambda chain: getattr(chain, 'name', '').lower())
        print("Доступные сети:")
        columns = 5
        for i in range(0, len(chains_list), columns):
            row_chains = chains_list[i:i + columns]
            row_str = "".join(
                f"{chain.name:<25}" if hasattr(chain, 'name') else "Unknown         "
                for chain in row_chains
            )
            print(row_str)
        return None, None

    logger.success(f"Найдены обе цепочки: {input_chain.name} -> {output_chain.name}")
    return input_chain, output_chain

@retry(max_attempts=3, delay=1)
def request_gas_zip(
    method: str = "GET",
    url: str = None,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = 10,
) -> Optional[Box]:
    """Выполняет HTTP-запрос с повторами и возвращает ответ в виде Box."""
    try:
        response = requests.request(
            method=method,
            url=url,
            json=json,
            params=params,
            timeout=timeout
        )
        response.raise_for_status()
        return Box(response.json())
    except requests.exceptions.HTTPError as errh:
        logger.error(f"HTTP Error: {errh}")
        raise  # Важно! Передаем исключение декоратору для повтора
    except requests.exceptions.ConnectionError as errc:
        logger.error(f"Ошибка подключения: {errc}")
        raise
    except requests.exceptions.Timeout as errt:
        logger.error(f"Таймаут запроса: {errt}")
        raise
    except requests.exceptions.RequestException as err:
        logger.error(f"Неизвестная ошибка: {err}")
        raise
    except ValueError as err:
        logger.error(f"Ошибка парсинга JSON: {err}")
    return None

def get_quote(input_chain: Box, output_chain:Box, deposit_wei, from_address, to_address):
    """

    :param input_chain:
    :param output_chain:
    :param deposit_wei:
    :param from_address:
    :param to_address:
    :return:
    """
    base_url = "https://backend.gas.zip/v2/quotes"
    deposit_chain = input_chain.chain
    outbound_chain = output_chain.chain
    full_url = f"{base_url}/{deposit_chain}/{deposit_wei}/{outbound_chain}"
    params = {'from': from_address,'to': to_address}

    try:
        response = request_gas_zip(url=full_url, params=params)
        return response
    except Exception as error:
        logger.error(f"Ошибка при получении квоты {error}")
        return None

def search_chain(chain_id,chains_list:Box):
    """
    Получаем список rpc
    :param chain_id:
    :param chains_list:
    :return list of Box:
    """
    for chain in chains_list:
        if chain_id == chain.chainId:
            return BoxList(chain.rpc)
    return None


