launch:
	./launch.sh

# serve to a Parallels VM browser (e.g. testing in Edge)
# binds only the Mac<->VM private network, not public wifi
# in the VM, browse to http://10.211.55.2:5012
launch-vm:
	./launch.sh --vm-host

launch-profiling:
	./launch.sh --scan-profiling

launch-profiling-no-parallel:
	./launch.sh --scan-profiling --no-parallel

# for temporary local builds
# to use: make run
run:
	docker build . -f Dockerfile.dev -t skrutable-app:debug
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
	ngrok http 5012
