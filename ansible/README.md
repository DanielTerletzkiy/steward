# Ansible collection `danielterletzkiy.steward`

Sets up [Steward](https://github.com/DanielTerletzkiy/steward)'s kitchen terminal on a Raspberry Pi.

| Role | |
|---|---|
| [`danielterletzkiy.steward.kiosk`](roles/kiosk/README.md) | Installs the Steward Kiosk app, pairs it with Steward and starts it full screen with the desktop |

The collection needs ansible-core 2.15 or newer, and nothing besides `ansible.builtin`.

## Install

From the GitHub release (the version matches Steward's):

```bash
ansible-galaxy collection install https://github.com/DanielTerletzkiy/steward/releases/download/v0.5.0/danielterletzkiy-steward-0.5.0.tar.gz
```

Or in `requirements.yml`:

```yaml
collections:
  - name: https://github.com/DanielTerletzkiy/steward/releases/download/v0.5.0/danielterletzkiy-steward-0.5.0.tar.gz
    type: url
```

Straight from git works too:

```bash
ansible-galaxy collection install 'git+https://github.com/DanielTerletzkiy/steward.git#/ansible,v0.5.0'
```

## Use

```yaml
- name: Kitchen terminal
  hosts: kitchen
  become: true
  roles:
    - role: danielterletzkiy.steward.kiosk
      vars:
        steward_kiosk_url: http://homeassistant.local:8095
        steward_kiosk_user: pi
```

The first time, pass a pairing code from Steward → Settings → Kitchen terminals:

```bash
ansible-playbook kitchen.yml -e steward_kiosk_pairing_code=ABCD-EFGH
```

`ansible-doc -t role danielterletzkiy.steward.kiosk` lists every variable.
