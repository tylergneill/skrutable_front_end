# for temporary local builds
# to use: make run
run:
	docker build . -f Dockerfile.stg -t skrutable-app:debug
	docker run \
	  --rm \
	  -it \
	  -p 5012:5012 \
	  --name skrutable-dev \
	  skrutable-app:debug


# for official stg and prod builds uploaded to Docker Hub
# to use: VERSION={version} make run-official
run-official:
	docker run \
	  --rm \
	  -it \
	  -p 5010:5010 \
	  --name skrutable-app \
	  tylergneill/skrutable-app:$(VERSION)

ngrok:
	ngrok http --request-header-add="ngrok-skip-browser-warning: true" 5012
