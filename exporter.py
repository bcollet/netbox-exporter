#!/usr/bin/env python3

import argparse
import ipaddress
import os
import pynetbox
import sys
import yaml
import re
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

config = os.path.join(os.path.dirname(os.path.realpath(__file__)),'config.yml')

with open(config, 'r') as ymlfile:
    cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)

templates_dir = os.path.dirname(os.path.realpath(__file__))

def ptr(nb, args):
    device_primary = {}
    device_cluster = {}
    vm_primary = {}
    records = {}
    serial = 0
    af = ipaddress.ip_network(args.prefix).version

    devices = nb.dcim.devices.all()
    vms = nb.virtualization.virtual_machines.filter(has_primary_ip=True)
    addresses = nb.ipam.ip_addresses.filter(parent=args.prefix)

    for device in devices:
        last_updated = int(datetime.timestamp(datetime.strptime(device.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        if device.virtual_chassis:
            device_cluster[device.id] = device.virtual_chassis.name

        if af == 4 and device.primary_ip4:
            device_primary[device.id] = device.primary_ip4.id

        elif af == 6 and device.primary_ip6:
            device_primary[device.id] = device.primary_ip6.id

    for vm in vms:
        last_updated = int(datetime.timestamp(datetime.strptime(vm.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        if af == 4 and vm.primary_ip4:
            vm_primary[vm.id] = vm.primary_ip4.id

        elif af == 6 and vm.primary_ip6:
            vm_primary[vm.id] = vm.primary_ip6.id

    for address in addresses:
        last_updated = int(datetime.timestamp(datetime.strptime(address.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        ip = ipaddress.ip_interface(address.address).ip
        ptr = ipaddress.ip_address(ip).reverse_pointer

        if address.dns_name:
            records[ptr] = [{"type":"PTR","rr":address.dns_name}]

        elif address.assigned_object_type == 'dcim.interface':
            if address.assigned_object.device.id in device_cluster:
                address.assigned_object.device.name = device_cluster[address.assigned_object.device.id]

            if address.assigned_object.device.id in device_primary and address.id == device_primary[address.assigned_object.device.id]:
                records[ptr] = [{"type":"PTR","rr":address.assigned_object.device.name}]
            else:
                iname = re.sub(r'[^a-z0-9]', '-',address.assigned_object.name)
                records[ptr] = [{"type":"PTR","rr":".".join((iname,address.assigned_object.device.name))}]

        elif address.assigned_object_type == 'virtualization.vminterface':
            if address.assigned_object.virtual_machine.id in vm_primary and address.id == vm_primary[address.assigned_object.virtual_machine.id]:
                records[ptr] =  [{"type":"PTR","rr":address.assigned_object.virtual_machine.name}]
            else:
                iname = re.sub(r'[^a-z0-9]', '-',address.assigned_object.name)
                records[ptr] = [{"type":"PTR","rr":".".join((iname,address.assigned_object.virtual_machine.name))}]

    file_loader = FileSystemLoader(templates_dir)
    env = Environment(loader=file_loader)
    template = env.get_template("zonefile.jj2")
    output = template.render(serial=serial,records=records)

    if not hasattr(args, 'output'):
        print(output)
    else:
        f = open(args.output,'w')
        f.write(output)
        f.close()

def dns(nb, args):
    devices_id = []
    vm_id = []
    primary_ip = {}
    records = {}
    serial = 0

    devices = nb.dcim.devices.filter(name__iew=args.domain)
    vms = nb.virtualization.virtual_machines.filter(name__iew=args.domain)
    addresses = nb.ipam.ip_addresses.all()

    for device in devices:
        last_updated = int(datetime.timestamp(datetime.strptime(device.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        devices_id.append(device.id)

        if device.primary_ip4:
            primary_ip[device.primary_ip4.id] = device.name

        if device.primary_ip6:
            primary_ip[device.primary_ip6.id] = device.name

    for vm in vms:
        last_updated = int(datetime.timestamp(datetime.strptime(vm.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        vm_id.append(vm.id)

        if vm.primary_ip4:
            primary_ip[vm.primary_ip4.id] = vm.name

        if vm.primary_ip6:
            primary_ip[vm.primary_ip6.id] = vm.name

    for address in addresses:
        last_updated = int(datetime.timestamp(datetime.strptime(address.last_updated, '%Y-%m-%dT%H:%M:%S.%fZ')))
        if last_updated > serial: serial = last_updated

        ip = ipaddress.ip_interface(address.address).ip
        if ipaddress.ip_address(ip).version == 4:
            type = "A"
        else:
            type = "AAAA"

        if address.dns_name and address.dns_name.endswith(args.domain):
            if address.dns_name not in records:
                records[address.dns_name] = []

            records[address.dns_name].append({"type":type,"rr":ip})

        elif address.id in primary_ip:
            if primary_ip[address.id] not in records:
                records[primary_ip[address.id]] = []

            records[primary_ip[address.id]].append({"type":type,"rr":ip})

        elif address.assigned_object_type == 'dcim.interface' and address.assigned_object.device.id in devices_id:
            iname = re.sub(r'[^a-z0-9]', '-',address.assigned_object.name.lower())
            fname = ".".join((iname,address.assigned_object.device.name))

            if fname not in records:
                records[fname] = []
            records[fname].append({"type":type,"rr":ip})

        elif address.assigned_object_type == 'virtualization.vminterface' and address.assigned_object.virtual_machine.id in vm_id:
            iname = re.sub(r'[^a-z0-9]', '-',address.assigned_object.name.lower())
            fname = ".".join((iname,address.assigned_object.virtual_machine.name))

            if fname not in records:
                records[fname] = []
            records[fname].append({"type":type,"rr":ip})

    file_loader = FileSystemLoader(templates_dir)
    env = Environment(loader=file_loader)
    template = env.get_template("zonefile.jj2")
    output = template.render(serial=serial,records=records)

    if not hasattr(args, 'output'):
        print(output)
    else:
        f = open(args.output,'w')
        f.write(output)
        f.close()

def autodns(nb, args):
    if not 'zones' in cfg:
        return

    for zone in cfg['zones']:
        if zone['type'] == 'reverse':
            ptr(nb, argparse.Namespace(prefix=zone['name'],output=zone['file']))
        elif zone['type'] == 'forward':
            dns(nb, argparse.Namespace(domain=zone['name'],output=zone['file']))


if __name__ == '__main__':
    nb = pynetbox.api(
        cfg['netbox']['url'],
        token=cfg['netbox']['token']
    )

    parser = argparse.ArgumentParser(description='Netbox API exporter')
    subparsers = parser.add_subparsers(help='Action to perform',dest='action',required=True)

    subparser = subparsers.add_parser('autodns', help='Generate all DNS zone files using configuration')

    subparser = subparsers.add_parser('ptr', help='Generate reverse DNS zone file for prefix')
    subparser.add_argument('prefix', type=str, help='Prefix')

    subparser = subparsers.add_parser('dns', help='Generate DNS zone file for domain')
    subparser.add_argument('domain', type=str, help='Domain')

    args = parser.parse_args()
    globals()[args.action](nb, args)
