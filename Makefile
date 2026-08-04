.PHONY: demo test verify

demo:
	PYTHONPATH=src python3 demo.py

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v


verify:
	PYTHONPATH=src python3 demo.py --list fixtures/second_list.json
