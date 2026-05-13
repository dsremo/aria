# ARIA Screener — operator helper.
#
# Round-2 audit NEW-MED-20 — `make secrets` creates each Docker secret
# file with strict 0600 perms.  Run before the first `docker compose
# up`; rotate via `make rotate-secrets`.

.PHONY: secrets rotate-secrets pin-image

SECRETS_DIR := ./secrets
SECRET_FILES := admin_token.txt master_key.txt oauth_state.txt hkdf_salt.txt tenant_key_hmac.txt

secrets:
	@mkdir -p $(SECRETS_DIR)
	@chmod 0700 $(SECRETS_DIR)
	@for f in $(SECRET_FILES); do \
		if [ ! -f $(SECRETS_DIR)/$$f ]; then \
			python3 -c "import secrets;print(secrets.token_hex(32))" > $(SECRETS_DIR)/$$f ; \
			chmod 0600 $(SECRETS_DIR)/$$f ; \
			echo "[generated] $(SECRETS_DIR)/$$f" ; \
		else \
			chmod 0600 $(SECRETS_DIR)/$$f ; \
			echo "[exists]    $(SECRETS_DIR)/$$f (perms reset to 0600)" ; \
		fi ; \
	done

rotate-secrets:
	@for f in $(SECRET_FILES); do \
		python3 -c "import secrets;print(secrets.token_hex(32))" > $(SECRETS_DIR)/$$f ; \
		chmod 0600 $(SECRETS_DIR)/$$f ; \
		echo "[rotated] $(SECRETS_DIR)/$$f" ; \
	done
	@echo "Restart with: docker compose up -d --force-recreate"

pin-image:
	@if [ -z "$$IMAGE" ]; then echo "set IMAGE=aria-screener@sha256:..." ; exit 2 ; fi
	@echo "ARIA_SCREENER_IMAGE=$$IMAGE" > .env.image
	@echo "Wrote .env.image — load with 'export \$$(cat .env.image)'"
