
import Image from 'next/image';

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
                                <SessionItem.Root cluster={item}>
                                    <SessionItem.StatusIcon status="running" />
                                </SessionItem.Root>
                            </>
                        )
                    )
                }
            <div className="flex justify-end">
                <button className="border border-green-400 hover:bg-green-500 duration-00 p-2 mt-3 rounded-lg hover:bg-green-600 hover:text-white font-medium">Add New Proxmox Cluster</button>
            </div>
                
            </div>
        </>
        
        
    )
}