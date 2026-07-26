import { useParams } from 'react-router-dom'
import { PagePlaceholder } from '../components/PagePlaceholder'

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>()
  return (
    <PagePlaceholder
      title="Device Detail"
      description={`Simulated device ${id ?? '—'} telemetry and fault history.`}
    />
  )
}
