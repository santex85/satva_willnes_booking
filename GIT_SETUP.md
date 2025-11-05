# Git Repository готов к push

## Команды для первого коммита:

```bash
# Добавить все файлы (если еще не добавлены)
git add .

# Создать первый коммит
git commit -m "Initial commit: Satva Wellness Booking System"

# Добавить remote репозиторий (замените URL на ваш)
git remote add origin https://github.com/yourusername/satva-wellness-booking.git

# Push в GitHub
git push -u origin main
```

## Проверка перед push:

✅ Все файлы добавлены
✅ .gitignore настроен правильно
✅ .env файл не включен (только .env.example)
✅ Чувствительные данные вынесены в переменные окружения
✅ README.md обновлен
✅ LICENSE добавлен
✅ Миграции включены
✅ Кэш Python файлов очищен

## Важные замечания:

⚠️ Убедитесь, что вы не коммитите:
- .env файлы
- Пароли и секретные ключи
- Базы данных
- Файлы виртуального окружения
- Кэш Python (__pycache__)

