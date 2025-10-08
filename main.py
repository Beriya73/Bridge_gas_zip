import random
import time
from loguru import logger

from utils.blockchain import TransactionSender
from utils.config import config, private_keys, chains_list
from utils.functions import (search_two_chain,
                             request_gas_zip,
                             get_quote,
                             search_chain)


def main():
    """Основная функция программы."""
    # 1. Проверяем загрузку конфигурации
    if config is None or private_keys is None or chains_list is None:
        logger.error("Один или несколько конфигурационных файлов не загружены. Проверьте utils/config.py")
        return

    # 2. Получаем и проверяем настройки задержки
    try:
        min_delay, max_delay = config.TIMEOUT
        if not (isinstance(min_delay, int) and isinstance(max_delay, int) and 0 <= min_delay <= max_delay):
            raise ValueError("Значения TIMEOUT должны быть целыми числами, и min <= max.")
        logger.info(f"Задержка между кошельками установлена от {min_delay} до {max_delay} секунд.")
    except (AttributeError, TypeError, ValueError) as e:
        logger.error(
            f"Ошибка в конфигурации TIMEOUT в setting.yaml. Убедитесь, что он задан как [min, max]. Ошибка: {e}")
        return

    # 3. Настройка сетей
    url = "https://backend.gas.zip/v2/chains"
    data_chain = request_gas_zip(url=url)
    input_chain, output_chain = search_two_chain(data_chain)
    if input_chain is None or output_chain is None:
        logger.error("Не удалось определить входящую или выходящую сеть. Выходим!")
        return

    chain_rpc = search_chain(input_chain.chain, chains_list)
    if chain_rpc is None:
        logger.error(f"Не смог найти RPC для сети {input_chain.name} в файле chain_rpc.json")
        return

    # 4. Основной цикл по кошелькам
    for i, private_key in enumerate(private_keys):
        try:
            sender = TransactionSender(private_key, chain_rpc[0].url, input_chain)

            logger.info(f"[{i + 1}/{len(private_keys)}] Работаем с кошельком: {sender.address}")
            logger.info(f"Баланс: {sender.w3.from_wei(sender.balance, 'ether')} {input_chain.symbol}")

            # 5. Улучшенная проверка минимального баланса
            min_amount = int(input_chain.minOutboundNative)
            gas_buffer = sender.w3.to_wei(0.001, 'ether')  # Примерный буфер на газ

            if sender.balance < (min_amount + gas_buffer):
                logger.warning(
                    f"Баланс ({sender.w3.from_wei(sender.balance, 'ether')}) слишком мал для бриджа минимальной суммы ({sender.w3.from_wei(min_amount, 'ether')}) с учетом газа. Пропускаем.")
                continue

            # 6. Расчет суммы для отправки (с запасом)
            amount_to_send = int(sender.balance * 0.99)  # Отправляем 99%, чтобы оставить на газ
            logger.info(f"Планируем отправить ~99%: {sender.w3.from_wei(amount_to_send, 'ether')} {input_chain.symbol}")

            if amount_to_send < min_amount:
                logger.warning(
                    f"Рассчитанная сумма ({sender.w3.from_wei(amount_to_send, 'ether')}) меньше минимально допустимой ({sender.w3.from_wei(min_amount, 'ether')}). Пропускаем.")
                continue

            # 7. Получение quote и отправка
            quote_data = get_quote(input_chain, output_chain, amount_to_send, sender.address, sender.address)
            if quote_data is None:
                logger.error("Не удалось получить quote от API. Пропускаем кошелек.")
                continue
            sender.quote = quote_data

            tx_hash = sender.send_transaction()
            explorer_url = sender.input_chain.explorer.rstrip('/')
            logger.success(f"Транзакция успешно отправлена! Эксплорер: {explorer_url}/tx/0x{tx_hash.hex()}")

        except ValueError as e:
            logger.error(f"Проблема с кошельком: {e}")
        except Exception as e:
            logger.error(f"Произошла непредвиденная ошибка: {e}")

        # 8. Логика задержки
        if i < len(private_keys) - 1:
            delay = random.randint(min_delay, max_delay)
            logger.info(f"Пауза. Ждем {delay} секунд перед следующим кошельком...")
            time.sleep(delay)

    logger.success("Все кошельки успешно обработаны. Завершение работы.")


if __name__ == "__main__":
    main()