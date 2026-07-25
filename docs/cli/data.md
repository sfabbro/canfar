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

Every remote source uses its configured Storage Name. The reserved `local`
source addresses the machine where the command runs. Operands always use an
explicit mapped name and absolute path:

```text
Storage-Name:/absolute/path
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

## Output and accepted omissions

Data command stdout belongs to the embedded command; CANFAR does not prepend
the active-Server banner or add JSON/YAML envelopes. Diagnostics are written to
stderr.

This release intentionally provides no public CANFAR storage Python API, FUSE
mount, signed-URL extension, progress display, confirmation prompt, `:/path` or
bare-path shorthand, `active` alias, `canfar storage` alias, recursive removal,
or cross-source `mv` workflow.

## Upstream releases

CANFAR installs pinned, tagged releases of
[`vosfs`](https://github.com/shinybrar/vosfs/releases/tag/v0.7.0) and
[`fsspec-cli`](https://github.com/shinybrar/vosfs/releases/tag/fsspec-cli-v0.6.0).
CANFAR tests its composition, configuration, authentication, and output seams;
exhaustive filesystem-command and backend matrices remain in the upstream
project.
