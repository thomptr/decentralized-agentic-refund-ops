.PHONY: demo-refundops demo-infra-up demo-agents-up demo-agents-down demo-infra-down demo-clean

demo-refundops: demo-infra-up demo-agents-up
	@echo "System started. Run: uv run python apps/api/dev_publish_ticket.py"
	@echo "Then: uv run python apps/api/trace_case.py <correlation_id>"

demo-infra-up:
	docker compose -f infra/local/docker-compose.yml up -d

demo-agents-up:
	bash scripts/start-local-system.sh

demo-agents-down:
	bash scripts/stop-local-system.sh --keep-kafka

demo-infra-down:
	docker compose -f infra/local/docker-compose.yml down

demo-clean: demo-agents-down demo-infra-down
	rm -rf .local-run/
