import Image from 'next/image'
import Link from 'next/link'
import { Circle } from 'lucide-react'
import  { SessionItem } from '@/components/SessionItem';
import { SessionList } from '@/components/SessionList';
// const clusters = [
//   {
//     "domain": "10.0.30.9",
//     "http_port": 8006,
//     "user": "root@pam",
//     "name": "PVE-CLUSTER-02",
//     "mode": "cluster"
//   },
//   {
//     "domain": "10.0.30.139",
//     "http_port": 8006,
//     "user": "root@pam",
//     "name": "pve01proxbox",
//     "mode": "standalone"
//   }
// ]

export default async function Home() {

  
  

  return (
    <div className="p-5">
      <SessionList />
    </div>
  )
}
