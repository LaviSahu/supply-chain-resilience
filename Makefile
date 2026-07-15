.PHONY: demo test dashboard clean

PYTHON ?= python3
export PYTHONPATH := src

demo:
	$(PYTHON) -m resilience_radar demo

test:
	$(PYTHON) -m unittest discover -s tests -v

dashboard:
	$(PYTHON) -m resilience_radar dashboard

clean:
	rm -rf output/*.json output/*.html
	find . -type d -name '__pycache__' -not -path './.git/*' -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
