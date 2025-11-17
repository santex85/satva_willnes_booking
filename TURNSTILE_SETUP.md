# Инструкция по настройке Cloudflare Turnstile на dev сервере

## 1. Установка зависимости

На dev сервере выполните:

```bash
# Если используете Docker
docker compose exec web pip install django-cf-turnstile==0.1.0

# Или если используете виртуальное окружение
pip install django-cf-turnstile==0.1.0
```

Или обновите зависимости из requirements.txt:

```bash
pip install -r requirements.txt
```

## 2. Получение ключей Cloudflare Turnstile

1. Перейдите на https://dash.cloudflare.com/
2. Войдите в свой аккаунт Cloudflare
3. В меню выберите **Turnstile**
4. Нажмите **Add Site** (Добавить сайт)
5. Заполните форму:
   - **Site name**: Название вашего сайта (например, "Satva Wellness Dev")
   - **Domain**: Домен вашего dev сервера (например, `dev.example.com` или `localhost` для разработки)
   - **Widget mode**: Выберите **Managed** (рекомендуется) или **Non-interactive**
6. Нажмите **Create**
7. Скопируйте **Site Key** и **Secret Key**

## 3. Настройка переменных окружения

Добавьте ключи в переменные окружения на dev сервере.

### Если используете Docker Compose:

Отредактируйте файл `.env` или `docker-compose.yml`:

```bash
# В .env файле добавьте:
CF_TURNSTILE_SITE_KEY=ваш_site_key_здесь
CF_TURNSTILE_SECRET_KEY=ваш_secret_key_здесь
```

Или в `docker-compose.yml` в секции `environment`:

```yaml
environment:
  - CF_TURNSTILE_SITE_KEY=ваш_site_key_здесь
  - CF_TURNSTILE_SECRET_KEY=ваш_secret_key_здесь
```

### Если используете обычный сервер:

Добавьте в файл `.env` или экспортируйте в shell:

```bash
export CF_TURNSTILE_SITE_KEY=ваш_site_key_здесь
export CF_TURNSTILE_SECRET_KEY=ваш_secret_key_здесь
```

### Если используете systemd service:

Отредактируйте файл сервиса (например, `/etc/systemd/system/gunicorn.service`):

```ini
[Service]
Environment="CF_TURNSTILE_SITE_KEY=ваш_site_key_здесь"
Environment="CF_TURNSTILE_SECRET_KEY=ваш_secret_key_здесь"
```

Затем перезагрузите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

## 4. Перезапуск приложения

После установки зависимостей и настройки переменных окружения:

```bash
# Если используете Docker
docker compose restart web

# Если используете systemd
sudo systemctl restart gunicorn

# Или просто перезапустите сервер разработки
python manage.py runserver
```

## 5. Проверка работы

1. Откройте страницу регистрации специалистов: `/register/specialist/`
2. Убедитесь, что виджет Turnstile отображается на странице
3. Попробуйте зарегистрировать тестового специалиста
4. Проверьте, что регистрация проходит успешно

## 6. Тестирование защиты

Для проверки, что защита работает:

1. Откройте консоль браузера (F12)
2. Попробуйте отправить форму без прохождения капчи (удалите поле через консоль)
3. Должна появиться ошибка: "Error verifying CAPTCHA, please try again."

## Примечания

- **Тестовые ключи**: Если переменные окружения не установлены, система автоматически использует тестовые ключи Cloudflare для разработки
- **Безопасность**: Никогда не коммитьте реальные ключи в репозиторий. Используйте только переменные окружения
- **Домены**: Убедитесь, что домен вашего dev сервера добавлен в настройках Turnstile в Cloudflare

