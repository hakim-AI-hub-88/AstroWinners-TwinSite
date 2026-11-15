import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Distributions } from '@/components/TerrainViz'

const earth = { slope_deg: { n: 208, min: 0.07, p10: 0.15, median: 0.31, mean: 0.58, p90: 1.5, max: 3.19 }, local_relief_m: { n: 270, min: 679, p10: 701, median: 744, mean: 756, p90: 820, max: 993 } }
const mars = { slope_deg: { n: 49, min: 0.03, p10: 0.27, median: 0.67, mean: 1.51, p90: 4.28, max: 8.85 }, local_relief_m: { n: 81, min: -4510, p10: -4495, median: -4453, mean: -4397, p90: -4213, max: -3585 } }

describe('Distributions', () => {
  it('draws one labelled box per dataset and feature with sample sizes', () => {
    render(<Distributions sets={[{ name: 'earth', tone: '#e79d61', d: earth }, { name: 'mars', tone: '#70b5b2', d: mars }]} />)
    expect(screen.getAllByRole('img')).toHaveLength(4)
    expect(screen.getByRole('img', { name: /earth · n=208: min 0.07, p10 0.15, median 0.31/ })).toBeInTheDocument()
    expect(screen.getByText(/different vertical datums/)).toBeInTheDocument()
    expect(screen.getByText(/not instrument uncertainty/)).toBeInTheDocument()
  })
})
