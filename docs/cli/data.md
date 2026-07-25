# Data commands

Use `canfar data` to work with configured VOSpace Services and the local
filesystem through the embedded `fsspec-cli` command application.

## Install and authenticate

Data commands are included in the standard installation:

```bash
pip install canfar
canfar login cadc
```

## Address mapped sources

Every operand starts with a Storage Identifier: the handle of a configured
VOSpace Service, or the reserved `local` identifier for the machine where the
command runs. Operands always pair an identifier with an absolute path:

```text
storage-identifier:/absolute/path
local:/absolute/path
```

Every mapped source is available concurrently, regardless of the active Server
Selection. A default CADC login maps two VOSpace Services, `arc` and `vault`,
plus `local`:

```bash
canfar data ls -lh arc:/
canfar data ls -lh arc:/home/[username]
canfar data ls -lh vault:/
```

Use `ls -lh`, or the `ll -h` long-form command, for a human-readable listing.
The `-h` flag reports human-readable sizes and requires a long listing, so
`ls -h` on its own exits with `ls: -h: requires long listing`.

Operands must name a mapped source. Empty `:/path`, bare local paths such as
`/tmp/file`, and `active:/path` are all rejected; there is no `active` alias
and no `canfar storage` command.

## Copy files and directories

Copy one file between local and remote sources:

```bash
canfar data cp local:/absolute/path/file.fits arc:/home/[username]/file.fits
canfar data cp arc:/home/[username]/file.fits local:/absolute/path/file.fits
```

Copy between two VOSpace Services, for example a public test cutout from
`vault` into your `arc` home directory:

```bash
canfar data cp vault:/ALMA/test-data/cutouts/test-4d-cube-cutout.fits arc:/home/[username]/test-4d-cube-cutout.fits
canfar data ls -lh arc:/home/[username]/test-4d-cube-cutout.fits
```

Recursive copy is enabled for admitted local and remote source pairs:

```bash
canfar data cp -R local:/absolute/path/dataset arc:/home/[username]/dataset
```

The tagged upstream implementation builds a bounded manifest, copies files
through host-local staging when sources differ, and verifies destination
metadata. Recursive copy is not atomic and does not create a snapshot; inspect
the destination before removing any source data.

## Move data between sources

Cross-source `mv` is unsupported and exits with status 2:

```text
mv: cross-source move unsupported
```

Move a file between sources explicitly by copying it, verifying the
destination, and only then issuing a separate source removal:

```bash
canfar data cp vault:/folder/file.fits arc:/home/[username]/file.fits
canfar data ls -lh arc:/home/[username]/file.fits
canfar data rm vault:/folder/file.fits
```

Do not use this sequence as a one-command or atomic move.

Recursive removal is disabled by application policy, so `rm` accepts no `-R` or
`-r` flag at all and exits with status 2:

```text
No such option: -R
```

Because recursive directory removal is disabled, directory movement is not a
supported workflow in this release. Any future one-command relocation would be a
separately named, opt-in orchestration feature with stronger destination
verification and residual-state semantics—not portable `mv`.

## Cache data locally

### Directory listings

Directory listings are cached automatically. Each command builds and closes its
own filesystem, so a cached listing only ever serves the command that produced
it and can never return a listing that outlives it. Repeated lookups while one
command walks a tree are served without another round trip.

### Files and byte ranges

There is no CLI flag for caching file contents, but `vosfs` is a normal
[fsspec](https://filesystem-spec.readthedocs.io/) filesystem, so any fsspec
cache can wrap it from Python. On a CANFAR session, `/scratch` is fast local
disk and is the right place to point a cache; it is not backed up and is
cleared when the session ends, which is exactly what a cache wants.

Cache whole files under a named directory. The first read fetches over the
network, and later reads come from `/scratch`:

```python
from pathlib import Path

from fsspec.implementations.cached import WholeFileCacheFileSystem
from vosfs import VOSpaceFileSystem

vault = VOSpaceFileSystem(
    "https://cadc-west-01.canfar.net/vault",
    certfile=str(Path.home() / ".ssl" / "cadcproxy.pem"),
)
cached = WholeFileCacheFileSystem(fs=vault, cache_storage="/scratch/vault-cache")

data = cached.cat_file("/ALMA/test-data/cutouts/test-4d-cube-cutout.fits")
```

Use `SimpleCacheFileSystem` instead when you do not need the expiry and
staleness metadata that `WholeFileCacheFileSystem` keeps. Passing
`cache_storage` a list of directories tries each in order and treats only the
last as writable, so a shared read-only cache can back your own.

### Cache byte ranges

`vosfs` sends an HTTP `Range` header and uses the response when the byte
endpoint answers `206`, so a partial read such as `cat_file(path, start, end)`
transfers only the bytes you asked for. Range support is per-backend:

| Storage Identifier | Backend | Ranged reads |
| --- | --- | --- |
| `vault` | `minoc` | Yes — a partial read returns `206` and transfers only that slice |
| `arc` | Cavern | No — the whole object is fetched and sliced, which is correct but not cheaper |

Because a range is now a real partial transfer against `vault`, a block cache
is worth using there. `MMapCache` keeps fetched blocks in a sparse file, so
only the blocks you touch occupy disk:

```python
from fsspec.caching import MMapCache

path = "/ALMA/test-data/cutouts/test-4d-cube.fits"
size = vault.info(path)["size"]
blocks = MMapCache(
    blocksize=1 << 20,
    fetcher=lambda start, end: vault.cat_file(path, start, end),
    size=size,
    location="/scratch/vault-cache/test-4d-cube.blocks",
)

header = blocks._fetch(0, 2880)  # one FITS header block, one 1 MiB range request
```

Reading a FITS header from a 3.4 MB cube this way issues a single ranged
request and materialises one block of four; a second read of the same range is
served from `/scratch`. The saving is in bytes transferred rather than seconds
on small files, because VOSpace transfer negotiation dominates a short request.
It grows with file size, and matters most when many reads hit different parts
of one large cube.

Against `arc` a block cache still costs a whole download per block, so cache
whole files there instead.

The `blockcache` filesystem remains unavailable over a VOSpace Service. `Range`
is honoured for byte reads, not through the file-object path, so wrapping
`CachingFileSystem` still fails:

```text
AttributeError: 'StagedReadFile' object has no attribute 'blocksize'
```

Stacked caches do not help either: chaining them (`filecache::simplecache::`)
builds the layers, but the inner layer is never filled and never serves, so use
exactly one cache layer on your fastest local disk.

These caches use the synchronous filesystem interface. Build the filesystem
without `asynchronous=True`, as above.

## Output and accepted omissions

Data command stdout belongs to the embedded command; CANFAR does not prepend
the active-Server banner or add JSON/YAML envelopes. Diagnostics are written to
stderr.

The Python equivalent of these commands is documented in
[Data Access](../client/data.md).

This release intentionally provides no FUSE mount, signed-URL extension,
progress display, confirmation prompt, `:/path` or bare-path shorthand,
`active` alias, `canfar storage` alias, recursive removal, or cross-source `mv`
workflow.

## Upstream releases

CANFAR installs pinned, tagged releases of
[`vosfs`](https://github.com/shinybrar/vosfs/releases/tag/v0.8.0) and
[`fsspec-cli`](https://github.com/shinybrar/vosfs/releases/tag/fsspec-cli-v0.7.0).
CANFAR tests its composition, configuration, authentication, and output seams;
exhaustive filesystem-command and backend matrices remain in the upstream
project.
