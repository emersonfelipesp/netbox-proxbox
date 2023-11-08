import Image from 'next/image'
import Link from 'next/link'

export default function Home() {
  return (
    <>
      <div>Welcome to Proxmox Standalone Version!</div>
      <Link href="/cluster">Clusters</Link>
    </>
  )

}
