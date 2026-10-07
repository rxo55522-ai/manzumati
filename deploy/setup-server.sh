#!/usr/bin/env bash
# تجهيز سيرفر جديد (Ubuntu 22.04/24.04) لموقع منظومتي، مع تقفيل السيرفر نفسه.
# يتشغل مرة وحدة بصلاحية root:   sudo bash deploy/setup-server.sh manzumati.ly
#
# قبل ما تشغله: لازم تكون حاط مفتاح SSH متاعك في السيرفر ومجرّب تدخل بيه،
# لأن السكربت يقفل الدخول بكلمة السر.
set -euo pipefail

DOMAIN="${1:?اكتب الدومين، مثلاً: sudo bash deploy/setup-server.sh manzumati.ly}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then echo "لازم تشغله بـ sudo"; exit 1; fi
if [[ ! -s /root/.ssh/authorized_keys ]] && ! ls /home/*/.ssh/authorized_keys >/dev/null 2>&1; then
  echo "ما لقيتش أي مفتاح SSH. حط مفتاحك الأول، غير هذا تتقفل برّا السيرفر."; exit 1
fi

echo "== 1) تحديث النظام وتركيب البرامج =="
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
DEBIAN_FRONTEND=noninteractive apt-get -y install nginx python3 ufw fail2ban unattended-upgrades certbot

echo "== 2) التحديثات الأمنية تنزل لحالها =="
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== 3) SSH: مفاتيح بس، وممنوع root =="
cat > /etc/ssh/sshd_config.d/99-manzumati.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowAgentForwarding no
EOF
sshd -t && systemctl reload ssh || systemctl reload sshd

echo "== 4) الجدار الناري: بس 22 و 80 و 443 =="
ufw default deny incoming
ufw default allow outgoing
ufw limit 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "== 5) fail2ban: يحظر اللي يحاول يخمّن كلمات السر =="
cat > /etc/fail2ban/jail.d/manzumati.local <<'EOF'
[sshd]
enabled = true
maxretry = 4
bantime = 1h
findtime = 10m

[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 30m
EOF
systemctl restart fail2ban

echo "== 6) مستخدم خاص بالموقع بدون صلاحيات وبدون دخول =="
id manzumati >/dev/null 2>&1 || useradd --system --home /opt/manzumati --shell /usr/sbin/nologin manzumati
mkdir -p /opt/manzumati /var/www/manzumati /var/www/certbot
rsync -a --delete --exclude public --exclude '.git' "$SRC"/ /opt/manzumati/ 2>/dev/null || cp -a "$SRC"/. /opt/manzumati/
chown -R root:root /opt/manzumati
chown -R manzumati:manzumati /opt/manzumati/data /var/www/manzumati
chmod 755 /opt/manzumati /var/www/manzumati
# الكود نفسه ملك root ومش قابل للتعديل من مستخدم الموقع؛ بس البيانات ومجلد النشر
find /opt/manzumati -path /opt/manzumati/data -prune -o -type f -exec chmod 644 {} +

echo "== 7) أول بناء للموقع =="
(cd /opt/manzumati && sudo -u manzumati /usr/bin/python3 -m manzumati.build --out /var/www/manzumati --data /opt/manzumati/data)

echo "== 8) شهادة HTTPS =="
# إعداد مؤقت عشان certbot يقدر يتحقق
cat > /etc/nginx/sites-available/manzumati-acme <<EOF
server { listen 80; server_name $DOMAIN www.$DOMAIN; location /.well-known/acme-challenge/ { root /var/www/certbot; } location / { return 404; } }
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/manzumati-acme /etc/nginx/sites-enabled/manzumati-acme
nginx -t && systemctl reload nginx
certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" -d "www.$DOMAIN" --agree-tos --register-unsafely-without-email -n
rm -f /etc/nginx/sites-enabled/manzumati-acme

echo "== 9) إعداد nginx النهائي =="
sed "s/manzumati\.ly/$DOMAIN/g" /opt/manzumati/deploy/nginx.conf > /etc/nginx/sites-available/manzumati
ln -sf /etc/nginx/sites-available/manzumati /etc/nginx/sites-enabled/manzumati
nginx -t && systemctl reload nginx

echo "== 10) الفاحص كل 5 دقايق =="
cp /opt/manzumati/deploy/manzumati-checker.service /opt/manzumati/deploy/manzumati-checker.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now manzumati-checker.timer

echo "تمام. جرّب: https://$DOMAIN"
