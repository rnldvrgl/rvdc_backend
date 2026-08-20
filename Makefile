## Makefile helpers for local development (DB & cache)

.PHONY: analyze vacuum clear-cache

analyze:
	@docker compose -f docker-compose.yml -f docker-compose.override.yml exec db \
		psql -U $(DB_USER) -d $(DB_NAME) -c "ANALYZE;"

vacuum:
	@docker compose -f docker-compose.yml -f docker-compose.override.yml exec db \
		psql -U $(DB_USER) -d $(DB_NAME) -c "VACUUM ANALYZE;"

clear-cache:
	@docker compose -f docker-compose.yml -f docker-compose.override.yml exec api \
		python manage.py clear_cache
