import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LegalSynthesisPanel from '../src/components/LegalSynthesisPanel.vue'
import type { Synthesis } from '../src/types/api'

describe('LegalSynthesisPanel', () => {
  it('renders concept-tagged segments as ConceptHyperlink buttons, plain segments as text', () => {
    const synthesis: Synthesis = {
      article_version_id: 'av-1',
      generated_by: 'deterministic_template',
      text_segments: [
        { text: '上市公司应当设置', concept_id: null },
        { text: '董事会', concept_id: 'concept-board-id' },
        { text: '。', concept_id: null },
      ],
    }

    const wrapper = mount(LegalSynthesisPanel, { props: { synthesis } })

    // The concept segment must render as a clickable hyperlink, not raw text —
    // proves we consumed text_segments[] instead of doing client-side string parsing.
    const conceptButton = wrapper.find('button.concept-hyperlink')
    expect(conceptButton.exists()).toBe(true)
    expect(conceptButton.text()).toBe('董事会')

    expect(wrapper.text()).toContain('上市公司应当设置')
    expect(wrapper.text()).toContain('生成方式：deterministic_template')
  })

  it('renders no concept buttons when every segment is plain text', () => {
    const synthesis: Synthesis = {
      article_version_id: 'av-2',
      generated_by: 'deterministic_template',
      text_segments: [{ text: '纯文本，无概念命中。', concept_id: null }],
    }

    const wrapper = mount(LegalSynthesisPanel, { props: { synthesis } })
    expect(wrapper.findAll('button.concept-hyperlink')).toHaveLength(0)
  })
})
