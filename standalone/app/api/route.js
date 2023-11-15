const proxbox_domain = 'http://localhost:8800'

export async function GET() {
    const res = await fetch(proxbox_domain, {
            headers: {
                'Content-Type': 'application/json',
            },
        })

    const data = await res.json()

    return Response.json({ data })
}