.PHONY: test benchmark demo validate

test:
	python3 -m unittest discover -s tests -v

benchmark:
	python3 experiments/benchmark.py --output experiments/results/latest.json

demo:
	python3 scripts/make_demo.py

validate:
	python3 $${SKILL_CREATOR_DIR:?set SKILL_CREATOR_DIR}/scripts/quick_validate.py .
