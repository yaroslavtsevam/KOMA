# Инструкция по хостингу проекта без белого IP через NetBird

Данная инструкция описывает, как развернуть веб-интерфейс проекта на вашей **локальной машине** (находящейся за NAT, без публичного «белого» IP-адреса) и безопасно пробросить к нему доступ через собственный VPN-сервер **NetBird**, развернутый на VPS с белым IP и доменным именем.

Мы рассмотрим два сценария доступа:
1. **Приватный доступ (Zero Trust)** — приложение доступно только устройствам, подключенным к вашей сети NetBird.
2. **Публичный доступ (Reverse Proxy Tunnel)** — веб-интерфейс проксируется через ваш VPS с белым IP и доступен в интернете по вашему домену (например, `https://timplan.yourdomain.com`).

---

## Архитектура решения (Публичный доступ)

```mermaid
graph LR
    subgraph "Интернет (Public Internet)"
        Client[Браузер клиента]
    end

    subgraph "VPS (Белый IP + Домен)"
        Nginx[Reverse Proxy: Nginx / Caddy]
        NetBirdVPS[NetBird Client VPS]
    end

    subgraph "Локальная сеть / NAT"
        NetBirdLocal[NetBird Client Local]
        DockerApp[Приложение TimPlan: Port 8080]
    end

    Client -- "HTTPS (Порт 443)" --> Nginx
    Nginx -- "Проксирование через туннель NetBird (http://10.x.x.x:8080)" --> NetBirdVPS
    NetBirdVPS == "Шифрованный туннель WireGuard" == > NetBirdLocal
    NetBirdLocal -- "Локальный трафик" --> DockerApp
```

---

## Шаг 1: Подключение локальной машины и VPS к NetBird

Вам необходимо установить клиент NetBird как на **локальной машине** (где запускается Docker-контейнер с веб-интерфейсом), так и на **VPS** (где настроен ваш NetBird Control Plane/Management Server).

### 1. Установка NetBird-клиента

Выполните команду установки на обеих машинах:

**Для Linux (VPS и Linux-десктоп):**
```bash
curl -fsSL https://pkgs.netbird.io/install.sh | sh
```

**Для macOS (Локальная машина):**
```bash
brew install netbirdio/tap/netbird
# Или скачайте официальный GUI-клиент с сайта netbird.io
```

### 2. Регистрация в вашей self-hosted сети NetBird
Так как ваш сервер NetBird является self-hosted, при авторизации клиентов необходимо явно указывать адрес вашего Management Server (например, `https://netbird.yourdomain.com`):

```bash
# Выполните на локальной машине и на VPS
netbird up --management-url https://<ВАШ_ДОМЕН_NETBIRD>
```
После ввода команды консоль выдаст ссылку для входа в панель управления. Перейдите по ней и подтвердите добавление устройства.

### 3. Проверка статуса подключения
После успешной авторизации проверьте статус сети:
```bash
netbird status
```
Вы увидите список подключенных пиров и ваш IP-адрес в виртуальной сети NetBird (обычно из диапазона `10.x.x.x` или `100.x.x.x`).

> [!IMPORTANT]
> Запишите NetBird IP-адрес вашей **локальной машины** (например, `10.10.10.5`) и **VPS** (например, `10.10.10.1`).

---

## Шаг 2: Настройка привязки портов в Docker-контейнере

По умолчанию NiceGUI в Docker-композиции может слушать только локальный хост или все интерфейсы. Убедитесь, что порт `8080` доступен для интерфейса NetBird на локальной машине.

В файле [web/docker-compose.yml](file:///Users/godfreyspencer/Downloads/TimPlanningDocling/web/docker-compose.yml) секция `ports` должна быть настроена следующим образом:
```yaml
    ports:
      # Слушать порт 8080 на всех сетевых интерфейсах локальной машины (включая интерфейс NetBirdwt0)
      - "8080:8080"
```
Запустите приложение на локальной машине:
```bash
docker compose -f web/docker-compose.yml up -d
```

---

## Шаг 3: Настройка проксирования на VPS

Для того чтобы пользователи из интернета могли зайти на сайт, настроим веб-сервер (Nginx или Caddy) на VPS, который будет принимать внешние запросы по HTTPS и перенаправлять их в защищенный туннель NetBird на вашу локальную машину.

### Вариант А: Использование Caddy (Рекомендуемый и самый простой)

Caddy автоматически выпустит SSL-сертификат от Let's Encrypt и настроит перенаправление.

1. Установите Caddy на ваш VPS.
2. Откройте `/etc/caddy/Caddyfile` и добавьте блок конфигурации:

```caddy
timplan.yourdomain.com {
    # Перенаправляем все запросы на NetBird IP локальной машины
    reverse_proxy 10.10.10.5:8080 {
        # Поддержка WebSockets (необходимо для работы NiceGUI)
        header_up Host {host}
        header_up X-Real-IP {remote_host}
    }
}
```
*(Замените `timplan.yourdomain.com` на ваш домен для проекта, а `10.10.10.5` — на NetBird IP вашей локальной машины).*

3. Перезапустите Caddy:
```bash
sudo systemctl restart caddy
```

---

### Вариант Б: Использование Nginx

Если на VPS уже установлен Nginx:

1. Создайте файл конфигурации `/etc/nginx/sites-available/timplan` со следующим содержимым:

```nginx
server {
    listen 80;
    server_name timplan.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name timplan.yourdomain.com;

    # SSL сертификаты (можно сгенерировать с помощью certbot)
    ssl_certificate /etc/letsencrypt/live/timplan.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/timplan.yourdomain.com/privkey.pem;

    location / {
        # NetBird IP локальной машины
        proxy_pass http://10.10.10.5:8080; 
        
        # Настройки проксирования
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # КРИТИЧЕСКИ ВАЖНО для NiceGUI (WebSockets & Hot-Reload):
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Увеличенные таймауты для длинных соединений NiceGUI
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
```
*(Замените `10.10.10.5` на ваш NetBird IP).*

2. Активируйте конфигурацию и перезапустите Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/timplan /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Шаг 4: Безопасность и оптимизация (Best Practices)

### 1. Ограничение доступа через NetBird Access Control
По умолчанию все устройства в вашей сети Netbird могут общаться друг с другом напрямую. Если вы хотите сделать доступ **приватным** (без публикации в интернет через VPS), вы можете отключить публичный прокси-сервер на VPS. В этом случае вы сможете заходить в веб-интерфейс, просто введя в браузере `http://10.10.10.5:8080` (находясь при этом подлюченным к NetBird со своего ноутбука или телефона).

Вы можете настроить правила (Access Control Rules) в веб-интерфейсе NetBird, чтобы:
- Разрешить VPS обращаться к локальной машине только по порту `8080`.
- Запретить остальным участникам сети доступ к вашей локальной машине напрямую.

### 2. Настройка брандмауэра (UFW) на локальной машине
Рекомендуется закрыть порт `8080` для публичных запросов из внешней локальной сети (например, Wi-Fi роутера), оставив доступ только для интерфейса NetBird:

```bash
# Разрешить трафик на порт 8080 только через сетевой интерфейс NetBird (обычно wt0)
sudo ufw allow in on wt0 to any port 8080 proto tcp
# Закрыть порт 8080 для остальных локальных интерфейсов
sudo ufw deny 8080/tcp
```

### 3. Автозапуск
Убедитесь, что служба Netbird добавлена в автозапуск на локальной машине и VPS:
```bash
sudo systemctl enable netbird
```
Теперь, даже при перезагрузке локального компьютера или сервера, туннель восстановится автоматически.
