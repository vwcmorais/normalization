.PHONY: all build deploy push dockerlogin push_misc test refresh_staging

PROJECT_NAME=role-normalization

ifeq ($(BUILDKITE_BRANCH),)
BRANCH ?= $(shell git branch | grep '^*' | cut -d' ' -f'2-')
else
BRANCH ?= $(BUILDKITE_BRANCH)
endif

BUILD_VERSION_PREFIX ?= $(shell echo ${BRANCH} | tr '/' '_')
ifneq ($(BUILDKITE_BUILD_NUMBER),)
BUILD_NUMBER ?= $(BUILDKITE_BUILD_NUMBER)
endif
ifeq ($(BUILD_NUMBER),)
BUILD_ID = $(BUILD_VERSION_PREFIX)
else
BUILD_ID = $(BUILD_VERSION_PREFIX)-$(BUILD_NUMBER)
endif

# This is what we consider a development env:
ifeq ($(BUILDKITE),)
DOCKER_BUILD_ARGS += --build-arg USERID=$(shell id -u)
DOCKER_BUILD_ARGS += --build-arg GROUPID=$(shell id -g)
else
DOCKER_BUILD_ARGS += --build-arg BUILD_VERSION=$(BUILD_ID)
DOCKER_BUILD_ARGS += --build-arg GIT_COMMIT=$(BUILDKITE_COMMIT)
DOCKER_BUILD_ARGS += --build-arg BUILD_URL=$(BUILDKITE_BUILD_URL)
endif

all: build

# DockerHub Login
DH_USER = $(shell aws secretsmanager get-secret-value --secret-id 'dockerhub' | jq '.SecretString' --raw-output |  jq '.username' --raw-output)
DH_PWD = $(shell aws secretsmanager get-secret-value --secret-id 'dockerhub' | jq '.SecretString' --raw-output |  jq '.password' --raw-output)
dockerlogin:
	@echo 'Logging in to Docker Hub using SecretManager credentials'
	echo "$(DH_PWD)" | docker login -u "$(DH_USER)" --password-stdin

build:
	docker build --progress plain -t $(PROJECT_NAME):$(BUILD_ID) $(DOCKER_BUILD_ARGS) -f build/Dockerfile .

test:
	docker run \
		--ulimit nofile=65536:65536 \
		$(PROJECT_NAME):$(BUILD_ID) \
		entrypoints/tests.sh

REGISTRY_URL = $(shell aws ecr describe-repositories --max-items 1 --repository-names '$(PROJECT_NAME)' | jq -r '.repositories[0].repositoryUri')
push:
	@echo "Pushing the Docker image using $(BUILD_ID) as the image version ID"
	docker tag "$(PROJECT_NAME):$(BUILD_ID)" "$(REGISTRY_URL):$(BUILD_ID)"
	docker push "$(REGISTRY_URL):$(BUILD_ID)"
	docker image rm "$(REGISTRY_URL):$(BUILD_ID)"
ifneq ($(BUILD_ID),$(BUILD_VERSION_PREFIX))
	docker tag "$(PROJECT_NAME):$(BUILD_ID)" "$(REGISTRY_URL):$(BUILD_VERSION_PREFIX)"
	docker push "$(REGISTRY_URL):$(BUILD_VERSION_PREFIX)"
	docker image rm "$(REGISTRY_URL):$(BUILD_VERSION_PREFIX)"
endif

run:
	docker run --rm -d -p 8080:8080 --name $(PROJECT_NAME) $(PROJECT_NAME):$(BUILD_ID)

deploy/environments/dev/local_settings.json:
	cp deploy/environments/dev/local_settings-template.json deploy/environments/dev/local_settings.json

network:
	if ! ( docker network ls --filter name=rolenorm --format '{{ .Name }}' | grep rolenorm > /dev/null ); then docker network create rolenorm; fi

DEPLOY_ENVIRONMENT ?= local

start: start_api

start_mysql: network
	docker run -d \
		--network rolenorm \
		--name rolenorm-mysql \
		-e MARIADB_ROOT_PASSWORD=senhaforte \
		-d mariadb:10

ifeq ($(AWS_DEFAULT_REGION),)
AWS_DEFAULT_REGION ?= $(shell if [ -r ~/.aws/credentials ]; then grep -A 5 "\[$(AWS_PROFILE)\]" ~/.aws/credentials | grep region | cut -d'=' -f2 | awk '{printf $$1}'; else echo 'Undefined'; fi)
endif
AWS_ACCESS_KEY_ID ?= $(shell if [ -r ~/.aws/credentials ]; then grep -A 5 "\[$(AWS_PROFILE)\]" ~/.aws/credentials | grep aws_access_key_id | cut -d'=' -f2 | awk '{printf $$1}'; else echo 'Undefined'; fi)
AWS_SECRET_ACCESS_KEY ?= $(shell if [ -r ~/.aws/credentials ]; then grep -A 5 "\[$(AWS_PROFILE)\]" ~/.aws/credentials | grep aws_secret_access_key | cut -d'=' -f2 | awk '{printf $$1}'; else echo 'Undefined'; fi)
AWS_SESSION_TOKEN ?= $(shell if [ -r ~/.aws/credentials ]; then grep -A 5 "\[$(AWS_PROFILE)\]" ~/.aws/credentials | grep aws_session_token | cut -d'=' -f2 | awk '{printf $$1}'; else echo 'Undefined'; fi)


start_api: network deploy/environments/dev/local_settings.json
	docker run --rm -d \
    	--name api \
    	--network rolenorm \
    	-e DEPLOY_ENVIRONMENT="$(DEPLOY_ENVIRONMENT)" \
        -e AWS_DEFAULT_REGION=$(AWS_DEFAULT_REGION) \
        -e AWS_ACCESS_KEY_ID=$(AWS_ACCESS_KEY_ID) \
        -e AWS_SECRET_ACCESS_KEY=$(AWS_SECRET_ACCESS_KEY) \
        -e AWS_SESSION_TOKEN=$(AWS_SESSION_TOKEN) \
		-e ROLE_NORM_SECRETS="$$(cat deploy/environments/dev/local_settings.json)" \
		-p '0.0.0.0:8192:8192' \
    	--ulimit nofile=65536:65536 \
		--mount "type=bind,src=`pwd`/role_normalization,dst=/seek/role-normalization/role_normalization" \
    	$(PROJECT_NAME):$(BUILD_ID) \
    	entrypoints/api.sh -w 1

start_events_api: network deploy/environments/dev/local_settings.json
	docker run --rm -d \
    	--name events_api \
    	--network rolenorm \
    	-e DEPLOY_ENVIRONMENT="$(DEPLOY_ENVIRONMENT)" \
        -e AWS_DEFAULT_REGION=$(AWS_DEFAULT_REGION) \
        -e AWS_ACCESS_KEY_ID=$(AWS_ACCESS_KEY_ID) \
        -e AWS_SECRET_ACCESS_KEY=$(AWS_SECRET_ACCESS_KEY) \
        -e AWS_SESSION_TOKEN=$(AWS_SESSION_TOKEN) \
		-e ROLE_NORM_SECRETS="$$(cat deploy/environments/dev/local_settings.json)" \
		-p '0.0.0.0:8192:8192' \
    	--ulimit nofile=65536:65536 \
		--mount "type=bind,src=`pwd`/role_normalization,dst=/seek/role-normalization/role_normalization" \
    	$(PROJECT_NAME):$(BUILD_ID) \
    	entrypoints/events_api.sh

stop_api:
	- docker stop api

stop_events_api:
	- docker stop events_api

start_nginx: network
	docker run -d \
    	--name nginx \
		--restart always \
		--user root \
    	--network rolenorm \
    	-e DEPLOY_ENVIRONMENT="$(DEPLOY_ENVIRONMENT)" \
    	--ulimit nofile=65536:65536 \
    	--health-cmd "curl --fail http://127.0.0.1:80/healthcheck || exit 1" \
    	-p '80:80' \
    	$(PROJECT_NAME):$(BUILD_ID) \
    	entrypoints/openresty.sh

console:
	docker run -it \
    	--name apiconsole \
    	--network rolenorm \
    	-e DEPLOY_ENVIRONMENT="$(DEPLOY_ENVIRONMENT)" \
		--env-file deploy/environments/dev/docker.env \
    	--ulimit nofile=65536:65536 \
    	$(PROJECT_NAME):$(BUILD_ID) \
    	bash

stop:
	-docker container stop mysql
	-docker container stop api
	-docker container stop events_api
	-docker container stop nginx
	-docker container rm mysql
	-docker container rm api
	-docker container rm nginx


push_misc:
	@echo "Pushing auxiliary (filebeat and jaeger) images to ECR"
	docker pull "docker.elastic.co/beats/filebeat:7.10.0"
	docker tag "docker.elastic.co/beats/filebeat:7.10.0" "$(REGISTRY_URL):filebeat"
	docker push "$(REGISTRY_URL):filebeat"

refresh_staging:
	@echo 'Starting instance refresh for ASG role-normalization-api-staging'
	aws autoscaling start-instance-refresh --auto-scaling-group-name role-normalization-api-staging

