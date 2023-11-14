
import Image from 'next/image';
import Link from 'next/link';

import { SessionItem } from '@/components/SessionItem';


type TargetList = "netbox" | "proxmox"

interface SessionListProps {
    target?: TargetList
    children?: React.ReactNode
}

export async function SessionList ({ children, target }: SessionListProps) {
    const response = await fetch('http://localhost:8800/proxmox/sessions', {
        next: {
          revalidate: 30,
        }
      })
    
    const response_json = await response.json()
    console.log(response_json)

    return (
        <>
            <div className="flex justify-center py-2">
                <Image src="proxmox-logo.svg" alt="Proxmox Logo" width="300" height="200" />
            </div>
            <div className="divide-y">
                {
                    response_json.map(( item ) => (
                            <>
                                {/* <Link href={`/proxmox/${item.name}`}> */}
                                    <SessionItem.Root cluster={item}>
                                        <SessionItem.Icon status="running" />
                                    </SessionItem.Root>
                                {/* </Link> */}
                            </>
                        )
                    )
                }
                
            </div>
        </>
        
        
    )
}