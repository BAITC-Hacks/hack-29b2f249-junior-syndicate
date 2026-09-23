# Доступ к рабочей области

## Локальный запуск

Из корня проекта:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app/app.py
```

Если результатов ещё нет, после входа нажмите «Запустить анализ». Используется тот же `src.pipeline.run`, что и в `python run.py`, с теми же входами, критериями и CSV.

Нажмите «Создать аккаунт», укажите свой email и пароль длиной от 12 символов. Сохраните резервный код: он потребуется для восстановления без почтового сервиса. Email является идентификатором локального аккаунта; приложение не проверяет владение почтовым ящиком и не отправляет письма.

Пароль хранится как scrypt-хеш с индивидуальной случайной солью. Резервный код хранится как SHA-256-хеш. Пять неудачных попыток блокируют вход для этого email на минуту. Сессия ограничена 30 минутами без серверных действий и восемью часами общей длительности. Перезагрузка страницы создаёт новую сессию и требует входа. После восстановления старый пароль, резервный код и ранее открытые локальные сессии перестают действовать.

По умолчанию база находится в `.streamlit/users.sqlite3`, исключена из Git и отделена от обезличенных клиентов графа. Для тестов путь переопределяется через `MONEY_GRAPH_ACCOUNTS`. Самостоятельная регистрация предназначена для локального приложения, привязанного к `127.0.0.1`; это не корпоративная система разграничения доступа.

Сервер не передаёт граф, карточки и выгрузки неавторизованной сессии. HTML/CSS/JS содержат только оболочку. Аналитические данные поступают после проверки аккаунта.

## Google OpenID Connect

Локальный вход работает без внешних сервисов. Для Google владелец приложения должен создать OAuth client типа Web application в Google Cloud и настроить consent screen / разрешённых тестовых пользователей. В Authorized redirect URIs добавьте точный адрес приложения с `/oauth2callback`.

Создайте локальный `.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "REPLACE_WITH_A_RANDOM_SECRET"
client_id = "REPLACE_WITH_GOOGLE_CLIENT_ID"
client_secret = "REPLACE_WITH_GOOGLE_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Сгенерировать cookie_secret можно командой:

```powershell
.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Открывайте приложение на том же host/port, что указан в redirect_uri. Для другого порта обновите адрес и в Google Cloud, и в secrets.toml. Перезапустите Streamlit. Кнопка Google станет доступна при наличии client_id; для успешного входа нужны все значения выше. Authlib включён в зависимости.

Секреты не нужно отправлять в чат или коммитить. OIDC-сессия и cookie управляются Streamlit; выход вызывает `st.logout()`. Срок cookie Google-входа в Streamlit отличается от локальной сессии и может достигать 30 дней. Google-вход требует интернета, аналитический расчёт остаётся локальным.

Настоящий Google round-trip необходимо проверить после настройки собственных ключей. Без ключей кнопка отключена с пояснением.

## Проверка браузера

Фронтенд не требует npm, сборки или CDN. Это локальный Streamlit-компонент с SVG-графом. Для отдельного браузерного теста нужны установленный Chrome и `pip install playwright` в окружении проекта.

Запустите приложение с отдельной тестовой базой:

```powershell
$env:MONEY_GRAPH_ACCOUNTS = "$PWD/output/ui-qa-accounts.sqlite3"
.venv/Scripts/python.exe -m streamlit run app/app.py --server.port 8502
```

В другом терминале:

```powershell
$env:MONEY_GRAPH_TEST_URL = "http://127.0.0.1:8502"
.venv/Scripts/python.exe -m pytest tests/test_browser.py -q
```

Скриншоты сохраняются в `output/ui-*.png`. Тест создаёт отдельный локальный аккаунт и скачивает CSV. Без переменной MONEY_GRAPH_TEST_URL браузерный тест пропускается; обычные тесты авторизации и серверных контрактов выполняются командой `python -m pytest -q`.
