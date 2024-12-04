# Netbox DNS exporter

This script will generate forward and reverse DNS zones files based on Netbox data, according to the supplied configuration file.

The following records will be generated:
- An entry per device using its primary IP. If both IPv4 and IPv6 primary addresses are configured it will generate both A and AAAA records (as well as the corresponding PTR records).
- An entry per IP/IPv6 configured on a device interface (except those flagged as primary addresses), replacing all non letter/number characters with hyphens (`-`). For instance: interface `xe-0/1/0.42` on `my-router.example.com` will becomre `xe-0-1-0-42.my-router.example.com`.

All records can be overriden using Netbox's _DNS Name_ field.

All devices' names must be fully qualified for forward DNS zones to be generated.

This script will also try to retrieve from Netbox a config context named after the zone's name for additional records to be included in the generated zone file. If it exists, the config context must adhere to the following format:

```json
{
    "records": [
        {
            "data": "\"v=spf1 -all\"",
            "rr": "@",
            "type": "TXT"
        },
        {
            "data": "\"v=DMARC1;p=reject;sp=reject;adkim=s;aspf=s\"",
            "rr": "_dmarc",
            "type": "TXT"
        },
        {
            "data": "0 .",
            "rr": "@",
            "type": "MX"
        }
    ]
}
```
