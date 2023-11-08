

async function getData() {
    const res = await fetch('http://localhost:8800/proxmox/sessions', {
        'headers': {
            'Content-Type': 'application/json',
        }
    })

    if (!res.ok) {
        // This will activate the closest `error.js` Error Boundary
        throw new Error('Failed to fetch data')
    }

    return res.json()
}


async function Session({ sessions }) {

    return (
        <>
            {
                sessions.map(( session ) => (
                    <ul>
                        <li key={session.domain}>{session.domain}</li>
                        <li key={session.http_user}>{session.http_user}</li>
                        <li key={session.user}>{session.user}</li>
                        <li key={session.name}>{session.name}</li>
                        <li key={session.mode}>{session.mode}</li>
                    </ul>
                ))
            }
        </>
    )
        
    
}
export default async function Page() {
    const data = await getData()

    return (
        <div className="container">
            <h1>Proxmox Sessions</h1>
            <Session sessions={data} />
        </div>  
    )
}