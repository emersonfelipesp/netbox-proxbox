export default function Page(
    { params }: { params: { cluster_name: string } }
) {
    return <div>Cluster: {params.cluster_name}</div>
}