FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive WINEDEBUG=-all WINEARCH=win64 WINEPREFIX=/data/wine TZ=Australia/Adelaide
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    wine wine64 xvfb xauth openssh-server gosu python3 python3-bcrypt openssl acl curl ca-certificates tar gzip \
    lib32gcc-s1 libstdc++6:i386 libgcc-s1:i386 procps tini iproute2 \
    && rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd /opt/scum /data \
    && useradd --create-home --home-dir /home/scum --shell /usr/sbin/nologin --uid 1000 scum
COPY docker/entrypoint.sh docker/supervisor.py docker/user_accounts.py /opt/scum/
COPY docker/web/index.html /opt/scum/web/index.html
RUN chmod 0755 /opt/scum/entrypoint.sh && chmod 0644 /opt/scum/supervisor.py \
    && mkdir -p /etc/ssh/sshd_config.d
EXPOSE 7777/udp 7778/udp 7779/udp 7779/tcp 2222/tcp 8080/tcp
# Health checks validate dashboard + SFTP only; SCUM game joinability is separate.
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/ >/dev/null && ss -lnt | grep -q ':2222 '
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini","--","/opt/scum/entrypoint.sh"]
