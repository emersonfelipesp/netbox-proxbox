from netboxlabs.diode.sdk import DiodeClient
from netboxlabs.diode.sdk.ingester import (
    Device,
    Entity,
    IPAddress,
)


def main():
    with DiodeClient(
        target="grpc://localhost:8081",
        app_name="my-test-app",
        app_version="0.0.1",
        api_key="5a52c45ee8231156cb620d193b0291912dd15433",
    ) as client:
        entities = []

        """
        Ingest device with device type, platform, manufacturer, site, role, and tags.
        """

       
        device = Device(
            name="TESTE",
            device_type="Device Type A",
            platform="Platform A",
            manufacturer="Manufacturer A",
            site="Site ABC",
            role="Role ABC",
            serial="123456",
            asset_tag="123456",
            status="active",
            tags=["tag 1", "tag 2"],
        )
        
        
        #device = Device(name="Device A")
        
        ip_address = IPAddress(
            address="172.16.0.1/24",
        )

        print(f"device: {device}")

        #print(f"client: {client}")
        #print(f"client (dir): {dir(client)}")
        #print(f"client (version): {client._target}")
        #print(f"ip_address: {ip_address}")
        entities.append(Entity(ip_address=ip_address))
        #entities.append(Entity(ip_address=ip_address))

        response = client.ingest(entities=entities)
        print(f"response: {response}")
        if response.errors:
            print(f"Errors: {response.errors}")


if __name__ == "__main__":
    main()
