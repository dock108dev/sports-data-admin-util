/**
 * Unit tests for ChaptersSection (Phase 1 Issue 13).
 * 
 * These tests validate data wiring, not aesthetics.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { ChaptersSection } from '../ChaptersSection';
import type { ChapterEntry } from '@/lib/api/sportsAdmin/types';

const mockChapters: ChapterEntry[] = [
  {
    chapter_id: 'ch_001',
    play_start_idx: 0,
    play_end_idx: 4,
    play_count: 5,
    reason_codes: ['PERIOD_START'],
    period: 1,
    time_range: { start: '12:00', end: '8:00' },
    chapter_summary: 'LeBron scored early to give the Lakers a lead.',
    chapter_title: 'Lakers Start Strong',
    plays: [
      { play_index: 0, description: 'Jump ball', quarter: 1, game_clock: '12:00', play_type: 'jump_ball' },
      { play_index: 1, description: 'LeBron makes layup', quarter: 1, game_clock: '11:30', play_type: 'made_shot' },
      { play_index: 2, description: 'Curry misses 3-pointer', quarter: 1, game_clock: '11:00', play_type: 'missed_shot' },
      { play_index: 3, description: 'LeBron makes dunk', quarter: 1, game_clock: '10:30', play_type: 'made_shot' },
      { play_index: 4, description: 'Timeout: Lakers', quarter: 1, game_clock: '8:00', play_type: 'timeout' },
    ],
  },
  {
    chapter_id: 'ch_002',
    play_start_idx: 5,
    play_end_idx: 7,
    play_count: 3,
    reason_codes: ['TIMEOUT'],
    period: 1,
    time_range: { start: '8:00', end: '5:00' },
    chapter_summary: 'The Warriors responded with a run.',
    chapter_title: 'Warriors Answer',
    plays: [
      { play_index: 5, description: 'Curry makes 3-pointer', quarter: 1, game_clock: '7:30', play_type: 'made_shot' },
      { play_index: 6, description: 'Durant makes layup', quarter: 1, game_clock: '7:00', play_type: 'made_shot' },
      { play_index: 7, description: 'Curry makes 3-pointer', quarter: 1, game_clock: '5:00', play_type: 'made_shot' },
    ],
  },
];

// Test 1: Chapters Render Test

describe('ChaptersSection - Rendering', () => {
  it('should render correct chapter count', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Should show chapter count in title
    expect(screen.getByText(/Chapters \(2\)/)).toBeInTheDocument();
  });

  it('should render all chapters in order', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Should show both chapter titles
    expect(screen.getByText('Lakers Start Strong')).toBeInTheDocument();
    expect(screen.getByText('Warriors Answer')).toBeInTheDocument();
  });

  it('should render chapter summaries', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Should show summaries
    expect(screen.getByText(/LeBron scored early/)).toBeInTheDocument();
    expect(screen.getByText(/Warriors responded/)).toBeInTheDocument();
  });

  it('should render empty state when no chapters', () => {
    render(<ChaptersSection chapters={[]} gameId={1} />);
    
    expect(screen.getByText(/No chapters generated yet/)).toBeInTheDocument();
  });
});

// Test 2: Expand Chapter Test

describe('ChaptersSection - Expansion', () => {
  it('should expand chapter when clicked', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Initially plays should not be visible
    expect(screen.queryByText('Jump ball')).not.toBeInTheDocument();
    
    // Click chapter header
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Now plays should be visible
    expect(screen.getByText('Jump ball')).toBeInTheDocument();
  });

  it('should show all plays in correct order', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Expand first chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Should show all 5 plays
    expect(screen.getByText('Jump ball')).toBeInTheDocument();
    expect(screen.getByText('LeBron makes layup')).toBeInTheDocument();
    expect(screen.getByText('Curry misses 3-pointer')).toBeInTheDocument();
    expect(screen.getByText('LeBron makes dunk')).toBeInTheDocument();
    expect(screen.getByText('Timeout: Lakers')).toBeInTheDocument();
  });

  it('should show play indices', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Expand first chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Should show play index 0
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('should collapse chapter when clicked again', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    
    // Expand
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    expect(screen.getByText('Jump ball')).toBeInTheDocument();
    
    // Collapse
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    expect(screen.queryByText('Jump ball')).not.toBeInTheDocument();
  });
});

// Test 3: Metadata Display

describe('ChaptersSection - Metadata', () => {
  it('should display reason codes', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Expand first chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Should show PERIOD_START reason code
    expect(screen.getByText('PERIOD_START')).toBeInTheDocument();
  });

  it('should display play range', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Expand first chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Should show play range
    expect(screen.getByText('0 - 4')).toBeInTheDocument();
  });

  it('should display time range', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Expand first chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Should show time range
    expect(screen.getByText('12:00 - 8:00')).toBeInTheDocument();
  });
});

// Test 4: Debug View

describe('ChaptersSection - Debug View', () => {
  it('should toggle debug view', () => {
    render(<ChaptersSection chapters={mockChapters} gameId={1} />);
    
    // Debug info should not be visible initially
    expect(screen.queryByText('Debug Info')).not.toBeInTheDocument();
    
    // Enable debug view
    const debugToggle = screen.getByLabelText(/Show Debug Info/);
    fireEvent.click(debugToggle);
    
    // Expand a chapter
    const chapterHeader = screen.getByText('Chapter 0').closest('div');
    if (chapterHeader) {
      fireEvent.click(chapterHeader);
    }
    
    // Debug info should now be visible
    expect(screen.getByText('Debug Info')).toBeInTheDocument();
  });
});
