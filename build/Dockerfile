FROM python:3.9-buster

ARG USERID=1111
ARG GROUPID=1111

RUN groupadd -g ${USERID} seek \
&& useradd -g ${GROUPID} -u ${USERID} -d /seek -m -s /bin/bash seek \
&& mkdir -p /seek/logs /seek/bin /seek/role-normalization \
&& chown -R seek:seek /seek

ENV DEBIAN_FRONTEND=noninteractive

# OpenResty
RUN apt-get install -y --no-install-recommends wget gnupg ca-certificates \
&& wget -O - https://openresty.org/package/pubkey.gpg | apt-key add - \
&& if ( uname -m | grep 'aarch64' ); then export ARMPATH="arm64/"; else export ARMPATH=""; fi \
&& echo "deb http://openresty.org/package/${ARMPATH}debian $(grep -Po 'VERSION=\"[0-9]+ \(\K[^)]+' /etc/os-release) openresty" > /etc/apt/sources.list.d/openresty.list \
&& apt-get update \
&& apt-get remove -y nginx \
&& apt-get install -y --no-install-recommends openresty

# Python dependencies (early, to fill cache)
RUN apt-get install -y libre2-dev
COPY --chown=${USERID}:${GROUPID} requirements.txt /seek/role-normalization/
RUN pip3 install -r /seek/role-normalization/requirements.txt

# Pre-download nltk data
RUN python3 -m nltk.downloader -d /usr/share/nltk_data stopwords rslp mac_morpho words

# Copying configuration files
RUN rm -f /etc/nginx/conf.d/*.conf
COPY deploy/environments/all/nginx.conf /usr/local/openresty/nginx/conf/nginx.conf

# Copy deploy config and entrypoints
COPY --chown=${USERID}:${GROUPID} deploy/entrypoints /seek/entrypoints
COPY --chown=${USERID}:${GROUPID} deploy/environments /seek/environments

# BUILD INFO
ARG BUILD_VERSION=undefined
ARG GIT_COMMIT=undefined
ARG BUILD_URL=undefined
LABEL BuildVersion=${BUILD_VERSION}
LABEL GitCommit=${GIT_COMMIT}
LABEL BuildUrl=${BUILD_URL}
LABEL Application=RoleNormalization
LABEL Brand=Catho
LABEL Project=RoleNormalization
LABEL Team=AIPS-AMERICAS
RUN echo "{ \
\"BuildVersion\": \"${BUILD_VERSION}\", \
\"GitCommit\": \"${GIT_COMMIT}\", \
\"BuildUrl\": \"${BUILD_URL}\", \
\"Application\": \"RoleNormalization\", \
\"Brand\": \"Catho\", \
\"Project\": \"RoleNormalization\", \
\"Team\": \"AIPS-AMERICAS\" \
}" > /seek/build_info.json

WORKDIR /seek
USER seek

# # Define docker healthcheck
# HEALTHCHECK --interval=30s --timeout=5s \
    # CMD curl --fail http://127.0.0.1:8192/healthcheck || exit 1

CMD ["/bin/bash", "-c", "/seek/entrypoints/api.sh"]

# Copy source code later to use docker cache as best as we can
COPY --chown=${USERID}:${GROUPID} role_normalization /seek/role-normalization/role_normalization
