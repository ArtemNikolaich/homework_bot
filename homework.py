import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()


PRACTICUM_TOKEN = os.getenv('YAP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TEL_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет наличие токенов для доступа к API и боту Telegram."""
    return all([TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.info('Отправка')
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )

        logging.debug(f'Сообщение отправлено {message}')

    except exceptions.TelegramError as error:
        logging.error(f'Ошибка при отправке сообщения: {error}')

    except Exception as error:
        logging.error(f'Неизвестная ошибка: {error}')


def get_api_answer(timestamp):
    """Отправляет запрос к API и возвращает ответ в формате json."""
    params_request = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }

    try:
        logging.info(
            'Начало запроса: url = {url},'
            'headers = {headers},'
            'params = {params}'.format(**params_request))

        homework_statuses = requests.get(**params_request)

        if homework_statuses.status_code != HTTPStatus.OK:
            raise exceptions.InvalidResponseCode(
                'Не удалось получить ответ API, '
                f'ошибка: {homework_statuses.status_code}'
                f'причина: {homework_statuses.reason}'
                f'текст: {homework_statuses.text}')
        return homework_statuses.json()

    except Exception:
        raise exceptions.ConnectionError(
            'Не верный код ответа параметра запроса: url = {url},'
            'headers = {headers},'
            'params = {params}'.format(**params_request))


def check_response(response):
    """
    Проверяет ответ API на наличие ключей 'status' и 'homeworks'.
    В случае отсутствия какого-либо ключа возбуждает исключение.
    """
    logging.debug('Проверка')

    if not isinstance(response, dict):
        raise TypeError('Ошибка в типе ответа API')

    if 'homeworks' not in response or 'current_date' not in response:
        raise exceptions.EmptyResponseFromAPI('Пустой ответ от API')

    homeworks = response.get('homeworks')

    if homeworks is None:
        raise TypeError('Homeworks не является списком')

    if not isinstance(homeworks, list):
        raise TypeError('Homeworks не является списком')

    return homeworks


def parse_status(homework):
    """Возвращает строку с сообщением о статусе проверки работы."""
    homework_name = homework.get('homework_name')
    status = homework.get('status')

    if not homework_name:
        raise ValueError('Ответ API не содержит ключ "homework_name"')

    if not status:
        raise ValueError(
            f'Статус работы "{homework_name}" не был возвращен API'
        )

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Статус работы "{homework_name}" неизвестен: {status}'
        )

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствует необходимое кол-во'
                         ' переменных окружения')
        sys.exit('Отсутсвуют переменные окружения')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    current_report = {
        'name': '',
        'output': ''
    }

    prev_report = current_report.copy()

    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get(
                'current_data', current_timestamp)
            new_homeworks = check_response(response)

            if new_homeworks:
                homework = new_homeworks[0]
                current_report['name'] = homework.get('homework_name')
                current_report['output'] = homework.get('status')

            else:
                homework = None
                current_report['output'] = 'Нет работ на проверке.'
            if current_report != prev_report:
                if homework is not None:
                    send = parse_status(homework)

                else:
                    send = current_report['output']
                send_message(bot, send)
                prev_report = current_report.copy()

            else:
                logging.debug('Статус не поменялся')

        except exceptions.NotForSending as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            current_report['output'] = message
            logging.error(message)

            if current_report != prev_report:
                send_message(bot, message)
                prev_report = current_report.copy

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s, %(levelname)s, '
            'Файл - %(filename)s, Функция - %(funcName)s, '
            'Номер строки - %(lineno)d, %(message)s'
        ),
        handlers=[logging.FileHandler('log.txt', encoding='UTF-8'),
                  logging.StreamHandler(sys.stdout)])
    main()
