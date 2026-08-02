# Runbook — the DERA backup mount

The second copy of the twelve monthly DERA packages lives on a separate 2 TB block device mounted
at `/mnt/backup`. Those packages are irreplaceable: SEC deletes a monthly file roughly twelve
months after publication, when the quarterly consolidation replaces it. Once deleted it cannot be
re-downloaded from anywhere.

This runbook covers making that mount survive a reboot, and verifying the copy after one.

---

## Current state

```
device      /dev/vdb
UUID        ebdbc746-b4c6-4199-9aee-f734fe08be02
LABEL       fintek-backup
filesystem  ext4
size        2.0 TB, 2.0 GB used
mount point /mnt/backup
```

**The mount is not persistent.** `/etc/fstab` contains no non-comment entries, and the
`mnt-backup.mount` unit systemd reports has `SourcePath=/proc/self/mountinfo` — a runtime object
synthesised from the live mount table, not a unit file on disk. After a reboot the device does not
remount and `/mnt/backup` is an empty directory on the root filesystem.

**The copied data is unaffected by this.** It is on the device, verified by SHA-256 and by ZIP CRC
on every member. The risk is not data loss; it is that a backup script writes into an empty
directory on the root disk after a reboot and reports success, leaving the real backup untouched
and stale while everything looks fine.

---

## Making it persistent

This requires root and is the only step in this runbook that changes the system.

### 1. Confirm the UUID still matches

```
lsblk -no NAME,UUID,LABEL,FSTYPE,SIZE /dev/vdb
```

Expect `ebdbc746-b4c6-4199-9aee-f734fe08be02` and `fintek-backup`. If it differs, the device was
reprovisioned — stop and re-verify the copy before changing anything.

### 2. Add the entry

```
sudo cp /etc/fstab /etc/fstab.bak
echo 'UUID=ebdbc746-b4c6-4199-9aee-f734fe08be02  /mnt/backup  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2' | sudo tee -a /etc/fstab
```

**By UUID, never by `/dev/vdb`.** Device names are assigned in discovery order and are not stable
across reboots or across adding a disk. An fstab entry naming `/dev/vdb` can mount a different
device at `/mnt/backup` after an unrelated change.

**`nofail` is not optional.** Without it, a missing or unreadable backup device fails the boot and
drops the host to an emergency shell. A second copy of an archive is not worth making the machine
unbootable. `x-systemd.device-timeout=10` bounds how long boot waits for a device that is not
coming back.

**`0 2` is the dump flag and the fsck pass.** Pass 2 means the filesystem is checked after the
root filesystem rather than in parallel with it.

### 3. Validate the entry BEFORE rebooting

An invalid fstab entry is discovered at boot, which is the worst possible time.

```
sudo umount /mnt/backup
sudo systemctl daemon-reload
sudo mount -a
findmnt -no SOURCE,TARGET,FSTYPE,OPTIONS /mnt/backup
```

The last command must print `/dev/vdb /mnt/backup ext4 rw,relatime`. If `mount -a` reports an
error, restore with `sudo cp /etc/fstab.bak /etc/fstab` and stop.

### 4. Verify the copy is intact

```
ls -1 /mnt/backup/dera/monthly/*.zip | wc -l     # expect 12
```

---

## After any reboot, before relying on the backup

```
findmnt /mnt/backup || echo "NOT MOUNTED — the backup path is an empty directory"
```

Never write a backup without this check. An unmounted `/mnt/backup` accepts writes onto the root
filesystem and reports success.

---

## Scope note

Making the mount persistent is **not** a Sprint 3 exit criterion. Criterion 12 asks that a second
durable copy of the twelve monthly packages exists, and it does — verified by hash on both sides
and by ZIP CRC on every member, on a device confirmed distinct by `stat`. Persistence is an
operational hardening step recorded here so it is not lost.
