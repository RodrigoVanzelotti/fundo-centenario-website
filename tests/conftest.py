import os

# Never read sender/payment credentials from a developer's .env during tests.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["APP_ENV"] = "development"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["PAYMENT_PROVIDER"] = "mock"
os.environ["EMAIL_ENABLED"] = "false"
