import time
from loguru import logger
import random
from utils.blockchain import TransactionSender
from utils.config import config, private_keys, chains_list
from utils.functions import (check_load_configuration,
                             search_two_chain,
                             request_gas_zip,
                             get_quote,
                             search_chain)


def main():
    """Основная функция программы."""

    # 1. Проверяем загрузку из файла config.yaml, private_keys.txt и chain_list.json
    if not check_load_configuration(config, private_keys, chains_list):
        logger.error("Выходим!")
        return

    # 2. Получаем и проверяем настройки задержки и таймаут
    try:
        min_delay, max_delay = config.TIMEOUT
        withdraw_max = config.WITHDRAW_MAX
        amount_out = config.AMOUNT_OUT
        if not (isinstance(min_delay, int) and isinstance(max_delay, int) and 0 <= min_delay <= max_delay):
            raise ValueError("Значения TIMEOUT должны быть целыми числами, и min <= max.")
        logger.info(f"Задержка между кошельками установлена от {min_delay} до {max_delay} секунд.")
    except (AttributeError, TypeError, ValueError) as e:
        logger.error(
            f"Ошибка в конфигурации TIMEOUT в setting.yaml. Убедитесь, что он задан как [min, max]. Ошибка: {e}")
        return

    # Проверяем параметры вывода нативной валюты
    if withdraw_max and any(amount_out):
        logger.error(f"Взаимоисключащие параметры WITHDRAW_MAX:{withdraw_max},"
                     f" amount_out:[{amount_out[0]},{amount_out[1]}], завершение...")
        return

    # 3. Получаем данные о всех поддерживаемых сетях в бридже Gas_zip
    url = "https://backend.gas.zip/v2/chains"
    support_chains = request_gas_zip(url=url)
    # Ищем входную и выходную сеть в поддерживаемых сетях
    input_chain, output_chain = search_two_chain(support_chains)

    if input_chain is None or output_chain is None:
        logger.error("Не удалось определить название сети. Выходим!")
        return
    # Проверка выходной сети на перевод средств
    # if not output_chain.inbound:
    #     logger.error(f"Перевод средств в сеть {config.OUTPUT_CHAIN} в настоящее время недоступен через Gas.zip")
    #     return

    # Получаем rpc для входной сети из списка всех сетей chain_list.org
    chain_rpc = search_chain(input_chain.chain, chains_list)
    if chain_rpc is None:
        logger.error(f"Не смог найти RPC для сети {input_chain.name} в файле chain_rpc.json")
        return

    # 4. Основной цикл по кошелькам

    for i, private_key in enumerate(private_keys):
        try:
            sender = None
            # Перебираем все доступные RPC для этой сети
            for rpc_item in chain_rpc:
                try:
                    current_url = rpc_item.url
                    # Пытаемся инициализировать отправителя
                    temp_sender = TransactionSender(private_key, current_url, input_chain)

                    # Делаем тестовый легкий запрос, чтобы проверить RPC (например, получить номер блока или chain_id)
                    # Если RPC мертвый, тут вылетит ошибка, и мы перейдем к следующему
                    temp_sender.w3.eth.get_block_number()

                    sender = temp_sender
                    break  # Если успешно, выходим из цикла перебора RPC
                except Exception as e:
                    logger.warning(f"RPC {current_url} не отвечает: {e}. Пробуем следующий...")

            if sender is None:
                logger.error(f"Не удалось подключиться ни к одному RPC для сети {input_chain.name}")
                continue

            logger.info(f"[{i + 1}/{len(private_keys)}] Работаем с кошельком: {sender.address}")
            logger.info(f"Баланс: {sender.w3.from_wei(sender.balance, 'ether')} {input_chain.symbol}")

            # 5. проверка минимального баланса
            min_amount = int(input_chain.minOutboundNative)
            # if withdraw_max:
            preliminary_amount = int(sender.balance * 0.95)  # Берем 95% для первичной оценки
            if amount_out:
                num = random.uniform(amount_out[0], amount_out[1])
                preliminary_amount = round(num, 6)

            # 6. Предварительный расчет: сначала запрашиваем quote для почти полного баланса
            quote_data = get_quote(input_chain, output_chain, preliminary_amount, sender.address, sender.address)
            if quote_data is None:
                logger.error("Не удалось получить quote от API. Пропускаем кошелек.")
                continue


            # 7. Оцениваем точную стоимость газа из quote
            try:
                gas_estimate = sender.w3.eth.estimate_gas({
                    'from': sender.address,
                    'to': sender.w3.to_checksum_address(quote_data.contractDepositTxn.to),
                    'value': int(quote_data.contractDepositTxn.value, 16),
                    'data': quote_data.contractDepositTxn.data,
                })

                # Получаем текущую цену газа
                latest_block = sender.w3.eth.get_block('latest')
                base_fee = latest_block['baseFeePerGas']
                max_priority_fee = sender.w3.eth.max_priority_fee
                max_fee = int(base_fee * 1.25 + max_priority_fee)

                # Рассчитываем максимальную стоимость газа с запасом 25%
                max_gas_cost = int(gas_estimate * 1.25) * max_fee

                # Вычисляем МАКСИМАЛЬНУЮ сумму для отправки
                amount_to_send = sender.balance - max_gas_cost

                logger.info(f"Оценка газа: {sender.w3.from_wei(max_gas_cost, 'ether')} {input_chain.symbol}")
                logger.info(
                    f"Максимальная сумма к отправке: {sender.w3.from_wei(amount_to_send, 'ether')} {input_chain.symbol}"
                    f" (~{input_chain.price * amount_to_send / 10 ** input_chain.decimals:.2f} USD)")

            except Exception as e:
                logger.error(f"Ошибка при оценке газа: {e}. Пропускаем кошелек.")
                continue

            # 8. Проверка минимальной суммы
            if amount_to_send < min_amount:
                logger.warning(
                    f"Сумма после вычета газа ({sender.w3.from_wei(amount_to_send, 'ether'):.6f}) "
                    f"меньше минимально допустимой ({sender.w3.from_wei(min_amount, 'ether'):.6f}). Пропускаем.")
                continue

            # 9. Получаем ФИНАЛЬНЫЙ quote с точной суммой
            final_quote = get_quote(input_chain, output_chain, amount_to_send, sender.address, sender.address)
            if final_quote is None:
                logger.error("Не удалось получить финальный quote от API. Пропускаем кошелек.")
                continue

            # 10. Отправка транзакции
            tx_hash = sender.send_transaction(final_quote)
            explorer_url = sender.input_chain.explorer.rstrip('/')
            logger.success(f"Транзакция успешно отправлена! Эксплорер: {explorer_url}/tx/{tx_hash.hex()}")

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