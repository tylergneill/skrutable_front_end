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

# --- Browser extension (extension/); see extension/README.md ---

EXT_VERSION = $(shell node -p "require('./extension/package.json').version")

# Build Chrome and Firefox into extension/dist/<browser>/ for Load unpacked.
extension-build:
	cd extension && npm ci --no-audit --no-fund && node build.cjs chrome && node build.cjs firefox

# Store builds: always the pinned npm library (any SKRUTABLE_JS_BUNDLE
# override is ignored), zipped as extension/dist/skrutable-extension-<browser>-<version>.zip.
extension-zip:
	cd extension && npm ci --no-audit --no-fund && \
	env -u SKRUTABLE_JS_BUNDLE node build.cjs chrome && \
	env -u SKRUTABLE_JS_BUNDLE node build.cjs firefox
	cd extension/dist && rm -f skrutable-extension-*-$(EXT_VERSION).zip && \
	(cd chrome && zip -qr ../skrutable-extension-chrome-$(EXT_VERSION).zip .) && \
	(cd firefox && zip -qr ../skrutable-extension-firefox-$(EXT_VERSION).zip .) && \
	ls -l skrutable-extension-*-$(EXT_VERSION).zip
