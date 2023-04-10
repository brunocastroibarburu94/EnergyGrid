pip-compile:
	pip-compile --resolver=backtracking --verbose --output-file=requirements.txt requirements.in
	pip-sync requirements.txt

pip-sync:
	pip-sync requirements.txt

lint-fix:
	black ./src

coverage_test:
	coverage run -m pytest ./test/ -v

coverage_html:
	coverage html

test_all:
	pytest ./test -v

test_grid_df:
	pytest ./test/test_grid_connection.py -v -k 'test_call_for_price_with_df'

test_grid_api:
	pytest ./test/test_grid_connection.py -v -k 'test_call_price_api'
	
test_grid_cache:
	pytest ./test/test_grid_connection.py -v -k 'test_consolidate_cache'

run:
	python src/build_cache.py
	

