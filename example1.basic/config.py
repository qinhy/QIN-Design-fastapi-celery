import sys
sys.path.append("..")
import os
import re

def find_advanced_config(possible_paths=None):
    # Define common paths where advanced.config might be located
    default_paths = [
        "/etc/rabbitmq/advanced.config",  # Linux
        os.path.expanduser("~/rabbitmq/advanced.config"),
        "C:\\ProgramData\\RabbitMQ\\advanced.config",  # Windows
        "C:\\Users\\%USERNAME%\\AppData\\Roaming\\RabbitMQ\\advanced.config"
    ]

    # Allow overriding default paths
    paths = possible_paths if possible_paths else default_paths

    for path in paths:
        expanded_path = os.path.expandvars(path)
        if os.path.isfile(expanded_path):
            return expanded_path

    return None


def set_consumer_timeout(config_path, timeout_ms):
    new_block = f'[\n  {{rabbit, [\n    {{consumer_timeout, {timeout_ms}}}\n  ]}}\n].\n'

    if not os.path.isfile(config_path) or os.path.getsize(config_path) == 0:
        # Create new file with only the consumer_timeout block
        with open(config_path, 'w', encoding='utf-8') as file:
            file.write(new_block)
        return config_path

    with open(config_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Clean up any dangling []. at the top
    content = re.sub(r'^\s*\[\]\.\s*', '', content)

    if "consumer_timeout" in content:
        content = re.sub(r'\{consumer_timeout,\s*\d+\}', f'{{consumer_timeout, {timeout_ms}}}', content)
        content = re.sub(r'\{consumer_timeout,\s*undefined\}', f'{{consumer_timeout, {timeout_ms}}}', content)
    else:
        rabbit_block_match = re.search(r'\{rabbit,\s*\[([^\]]*)\]\}', content, re.DOTALL)
        if rabbit_block_match:
            original_block = rabbit_block_match.group(0)
            inner_content = rabbit_block_match.group(1)
            new_inner = inner_content.strip()
            if new_inner and not new_inner.endswith(','):
                new_inner += ','
            new_inner += f'\n    {{consumer_timeout, {timeout_ms}}}'
            new_block = f'{{rabbit, [\n    {new_inner}\n]}}'
            content = content.replace(original_block, new_block)
        else:
            # No rabbit block found; just use the new block
            content = new_block

    with open(config_path, 'w', encoding='utf-8') as file:
        file.write(content)

    return config_path


def get_consumer_timeout(config_path):
    if not os.path.isfile(config_path):
        return None

    with open(config_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Search for the consumer_timeout value
    match = re.search(r'\{consumer_timeout,\s*(\d+|undefined)\}', content)
    if match:
        value = match.group(1)
        if value.isdigit():
            return int(value)
        else:
            return value  # likely 'undefined'
    return 1800000

def config():
    import os
    import requests
    os.environ.setdefault('CELERY_TASK_SERIALIZER', 'json')

    # for app back {redis | mongodbrabbitmq}
    APP_BACK_END = os.getenv('APP_BACK_END', 'redis')  # Defaulting to a common local endpoint
    APP_INVITE_CODE = os.getenv('APP_INVITE_CODE', '123')  # Replace with appropriate default
    APP_SECRET_KEY = os.getenv('APP_SECRET_KEY', 'super_secret_key')  # Caution: replace with a strong key in production

    # Constants with clear definitions
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))  # Use environment variable with a default fallback
    SESSION_DURATION = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    UVICORN_PORT = int(os.getenv('UVICORN_PORT', 8000))  # Using an environment variable fallback
    FLOWER_PORT = int(os.getenv('UVICORN_PORT', 5555))  # Using an environment variable fallback
    # External service URLs with sensible defaults
    RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'localhost:15672')
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'guest')
    RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'guest')
    RABBITMQ_CONSUMER_TIMEOUT = int(os.getenv('RABBITMQ_CONSUMER_TIMEOUT', '1800000'))
    if APP_BACK_END == 'mongodbrabbitmq':
        # Try reading the current consumer_timeout if config was previously found
        config_path = find_advanced_config()
        if config_path:
            current_timeout = int(get_consumer_timeout(config_path))
        else:
            raise ValueError("advanced.config file not found.")
        if RABBITMQ_CONSUMER_TIMEOUT!=current_timeout:
            print(f'[Important]: RABBITMQ_CONSUMER_TIMEOUT is {RABBITMQ_CONSUMER_TIMEOUT} and not the same in advanced.config, auto setting, need reboot.')
            set_consumer_timeout(config_path,RABBITMQ_CONSUMER_TIMEOUT)

    MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    MONGO_DB = os.getenv('MONGO_DB', 'tasks')

    CELERY_META = os.getenv('CELERY_META', 'celery_taskmeta')
    CELERY_RABBITMQ_BROKER = os.getenv('CELERY_RABBITMQ_BROKER', 'amqp://localhost')

    # Redis URL configuration with fallback
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Handle external IP fetching gracefully with error handling
    try:
        EX_IP = requests.get('https://v4.ident.me/').text
    except requests.RequestException:
        EX_IP = '127.0.0.1'  # Fallback to a default value if the request fails
    print('APP_BACK_END :',APP_BACK_END)
    print('APP_INVITE_CODE :',APP_INVITE_CODE)
    print('APP_SECRET_KEY :',APP_SECRET_KEY)
    print('ALGORITHM :',ALGORITHM)
    print('ACCESS_TOKEN_EXPIRE_MINUTES :',ACCESS_TOKEN_EXPIRE_MINUTES)
    print('SESSION_DURATION :',SESSION_DURATION)
    print('UVICORN_PORT :',UVICORN_PORT)
    print('FLOWER_PORT :',FLOWER_PORT)
    print('EX_IP :',EX_IP)

    if APP_BACK_END=='mongodbrabbitmq':
        print('RABBITMQ_URL :',RABBITMQ_URL)
        print('RABBITMQ_USER :',RABBITMQ_USER)
        print('RABBITMQ_PASSWORD :',RABBITMQ_PASSWORD)
        print('RABBITMQ_CONSUMER_TIMEOUT :',RABBITMQ_CONSUMER_TIMEOUT)

        print('MONGO_URL :',MONGO_URL)
        print('MONGO_DB :',MONGO_DB)

        print('CELERY_META :',CELERY_META)
        print('CELERY_RABBITMQ_BROKER :',CELERY_RABBITMQ_BROKER)
    if APP_BACK_END=='redis':
        # Redis URL configuration with fallback
        print('REDIS_URL :',REDIS_URL)
    return (APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,
            ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,
            FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,
            MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP)

APP_BACK_END,APP_INVITE_CODE,APP_SECRET_KEY,ALGORITHM,ACCESS_TOKEN_EXPIRE_MINUTES,SESSION_DURATION,UVICORN_PORT,FLOWER_PORT,RABBITMQ_URL,RABBITMQ_USER,RABBITMQ_PASSWORD,MONGO_URL,MONGO_DB,CELERY_META,CELERY_RABBITMQ_BROKER,REDIS_URL,EX_IP = config()
