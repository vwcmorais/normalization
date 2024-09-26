.PHONY: help default

TERRAFORM := terraform_1

default: help

help:
	@echo
	@echo "Basic available targets are in the form \"COMMAND/ENVIRONMENT/RELEASE\""
	@echo
	@echo "COMMAND is one of deploy, plan, destroy, refresh, corresponding"
	@echo "to terraform commands apply, plan, destroy, apply -refresh-only" 
	@echo "Use the \"new\" command to start a new environment or service workspace."
	@echo "If you get the error message \"Workspace XXXX doesn't exist\" you"
	@echo "probably need to run the \"new\" command for that environment/service"
	@echo
	@echo "ENVIRONMENT is one of the sub-dirs of the environments dir, like prod, staging..."
	@echo
	@echo "SERVICE is one of the sub-dirs of the services dir, like base, api, indexer, ..."
	@echo
	@echo "Usage examples:"
	@echo " make new/prod/api"
	@echo " make deploy/prod/api"
	@echo " make destroy/prod/api"
	@echo

tfcache/%:
	@if [ -d 'services/$(@F)/.terraform' ]; then \
		echo; \
		echo -n "Keep terraform local state/plugins dir (.terraform) ? [Y/n]:"; \
		read ANS; \
		if [ "$${ANS}" = "n" ]; then \
			rm -rf services/$(@F)/.terraform; \
			echo "Initializing terraform cache/plugins dir for service $(*D)"; \
			cd services/$(@F) && $(TERRAFORM) init; \
		fi \
	else \
		echo "Initializing terraform cache/plugins dir for service $(*D)"; \
		cd services/$(@F) && $(TERRAFORM) init; \
	fi

is_main_branch:
	@if ! ( git branch | grep '^* main$$' ); then \
		echo; \
    	echo "This script (and all terraform operations) should be done using the \"main\" branch."; \
    	echo "Switch to \"main\" branch and try again."; \
		echo; \
    	exit 1; \
	fi

upgrade/%: is_main_branch
	rm -rf services/$(@F)/.terraform
	cd services/$(@F) && $(TERRAFORM) init --upgrade

new/%: is_main_branch tfcache/%
	@echo "Creating terraform workspace for service $(@F) on environment $(*D)"
	cd services/$(@F) \
		&& $(TERRAFORM) workspace new $(*D)

apply/%: is_main_branch tfcache/%
	@echo "Running terraform deploy of service $(@F) on environment $(*D)"
	cd services/$(@F) \
		&& $(TERRAFORM) workspace select $(*D) \
		&& $(TERRAFORM) apply -var-file ../../environments/$(*D)/terraform.tfvars

deploy/%: apply/%
	@echo -n

plan/%: is_main_branch tfcache/%
	@echo "Planning terraform deploy of service $(@F) on environment $(*D)"
	cd services/$(@F) \
		&& $(TERRAFORM) workspace select $(*D) \
		&& $(TERRAFORM) plan -var-file ../../environments/$(*D)/terraform.tfvars

destroy/%: is_main_branch tfcache/%
	@echo "Destroying terraform deploy of service $(@F) on environment $(*D)"
	cd services/$(@F) \
		&& $(TERRAFORM) workspace select $(*D) \
		&& $(TERRAFORM) destroy -var-file ../../environments/$(*D)/terraform.tfvars

refresh/%: is_main_branch tfcache/%
	@echo "Planning terraform deploy of service $(@F) on environment $(*D)"
	cd services/$(@F) \
		&& $(TERRAFORM) workspace select $(*D) \
		&& $(TERRAFORM) apply -refresh-only -var-file ../../environments/$(*D)/terraform.tfvars

clean/%: is_main_branch
	@echo "Cleaning terraform state/plugins dir (.terraform) of service $(@F)"
	cd services/$(@F) \
		&& rm -rf .terraform .terraform.lock.hcl
