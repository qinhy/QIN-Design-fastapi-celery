import sys
sys.path.append("..")

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
