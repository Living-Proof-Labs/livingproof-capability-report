"""Resolve an anonymous registry manifest and render immutable release instructions."""
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

IMAGE = 'ghcr.io/living-proof-labs/livingproof-capability-report'


def resolve(version):
    repository = IMAGE.removeprefix('ghcr.io/')
    query = urllib.parse.urlencode({'service': 'ghcr.io', 'scope': f'repository:{repository}:pull'})
    with urllib.request.urlopen(f'https://ghcr.io/token?{query}') as response:
        token = json.load(response)['token']
    request = urllib.request.Request(f'https://ghcr.io/v2/{repository}/manifests/{version}', headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.oci.image.index.v1+json, '
                  'application/vnd.docker.distribution.manifest.list.v2+json'})
    with urllib.request.urlopen(request) as response:
        body = response.read()
        digest = response.headers['Docker-Content-Digest']
    if digest != 'sha256:' + hashlib.sha256(body).hexdigest():
        raise ValueError('Registry manifest digest does not match content')
    manifest = json.loads(body)
    platforms = sorted(f"{m['platform']['os']}/{m['platform']['architecture']}"
                       for m in manifest['manifests'])
    if platforms != ['linux/amd64', 'linux/arm64']:
        raise ValueError(f'Unexpected release platforms: {platforms}')
    return {'image': IMAGE, 'version': version, 'manifest_digest': digest,
            'platforms': platforms, 'manifests': manifest['manifests']}


def notes(record):
    reference = f"{record['image']}@{record['manifest_digest']}"
    return (f"\n## Container distribution\n\nImage: `{record['image']}:{record['version']}`.\n"
            f"Registry manifest digest: `{record['manifest_digest']}` (not a local image ID).\n"
            f"Platforms: {', '.join(record['platforms'])}.\n\n"
            f"```sh\ndocker pull {reference}\ndocker run --rm {reference} --version\n"
            f"docker run --rm -v \"$PWD/bundle:/data:ro\" {reference} validate /data/manifest.json\n```\n\n"
            f"For an explicit offline export, run `docker tag {reference} reporter-offline:{record['version']}` "
            f"then `docker save -o reporter-image.tar reporter-offline:{record['version']}` "
            "after pulling the desired platform. Routine releases do not attach "
            "image archives; existing release assets are preserved.\n")


if __name__ == '__main__':
    if sys.argv[1] == 'resolve':
        Path('registry.json').write_text(json.dumps(resolve(sys.argv[2]), indent=2) + '\n')
    else:
        print(notes(json.loads(Path(sys.argv[2]).read_text())))
