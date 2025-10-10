from typing import Callable

from box import Box
from eth_typing import Hash32, HexStr
from hexbytes import HexBytes
from web3 import Web3
from loguru import logger
from web3.types import TxReceipt


class TransactionSender:
    """
    Класс для подготовки, проверки и отправки транзакции для одного кошелька.
    """

    def __init__(self, private_key: str, rpc: str, input_chain: Box):
        self.private_key = private_key
        self.w3 = Web3(Web3.HTTPProvider(rpc))
        self.address = self.w3.to_checksum_address(self.w3.eth.account.from_key(private_key).address)
        self.balance = self.w3.eth.get_balance(self.address)
        self._quote = None
        self.input_chain = input_chain  # Сохраняем для ссылки на эксплорер

    @property
    def quote(self) -> Box:
        return self._quote

    @quote.setter
    def quote(self, new_quote: Box):
        """Сеттер для атрибута quote с проверкой."""
        if new_quote is None:
            raise ValueError("Quote не может быть пустым (None)")
        self._quote = new_quote

    def send_transaction(self) -> HexBytes:
        """
        Собирает, проверяет, подписывает и отправляет транзакцию.
        Возвращает хэш транзакции в случае успеха.
        """
        contractDepositTxn = self._quote.contractDepositTxn

        # 1. Получаем актуальные параметры газа (EIP-1559)
        latest_block = self.w3.eth.get_block('latest')
        base_fee = latest_block['baseFeePerGas']
        max_priority_fee_per_gas = self.w3.eth.max_priority_fee
        max_fee_per_gas = int(base_fee*1.25 + max_priority_fee_per_gas)

        # 2. Формируем базовые параметры транзакции
        tx_params = {
            'type': '0x2',
            'from': self.address,
            'to': self.w3.to_checksum_address(contractDepositTxn.to),
            'value': int(contractDepositTxn.value, 16),
            'data': contractDepositTxn.data,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'chainId': self.w3.eth.chain_id,
            'maxPriorityFeePerGas': max_priority_fee_per_gas,
            'maxFeePerGas': max_fee_per_gas
        }

        # 3. Надёжно оцениваем газ с запасом и обработкой ошибок
        try:
            gas_estimate = self.w3.eth.estimate_gas(tx_params)
            tx_params['gas'] = int(gas_estimate * 1.25)  # Добавляем запас 25%
            logger.info(f"Оценка газа: {gas_estimate}, с запасом: {tx_params['gas']}")
            # print(f"Basefee: {base_fee}")
            # print(f'maxFeePerGas: {max_fee_per_gas}')
            # print(f'maxPriorityFeePerGas: {max_priority_fee_per_gas}')
        except Exception as e:
            logger.error(f"Ошибка при оценке газа: {e}")
            raise ValueError("Не удалось оценить газ, транзакция не будет отправлена.")

        # # 4. Финальная проверка баланса перед отправкой
        # max_gas_cost = tx_params['gas'] * max_fee_per_gas
        # total_needed = tx_params['value'] + max_gas_cost
        #
        # if self.balance < total_needed:
        #     shortage = total_needed - self.balance
        #     logger.error(
        #         f"Недостаточно средств! Баланс: {self.w3.from_wei(self.balance, 'ether')},"
        #         f" Нужно: {self.w3.from_wei(total_needed, 'ether')}, Не хватает: {self.w3.from_wei(shortage, 'ether')}")
        #     raise ValueError("Недостаточно средств для отправки транзакции и оплаты газа")

        # 5. Подпись и отправка
        signed_tx = self.w3.eth.account.sign_transaction(tx_params, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash