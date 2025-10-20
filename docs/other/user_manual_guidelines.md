# EDGAR CLI User Manual - Guidelines and Structure

## Manual Objectives

### Primary Goal
Create a comprehensive user manual that transforms casual users into proficient financial analysts by providing both practical guidance and conceptual understanding of XBRL-based financial analysis.

### Target Audience
- **Primary**: Fundamental analysts without deep XBRL knowledge
- **Secondary**: Financial researchers seeking reproducible workflows
- **Tertiary**: Advanced users requiring automation and batch processing capabilities

## Core Manual Principles

### 1. Progressive Complexity
- Start with immediate utility ("Get balance sheet data in 30 seconds")
- Build toward sophisticated workflows ("Multi-company longitudinal analysis")
- Finish with advanced automation ("Journal-driven database management")

### 2. Explain the "Why" Not Just the "How"
- **XBRL Context**: Gentle explanation of why XBRL exists and its inherent challenges
- **Design Rationale**: Why the tool works the way it does (cache-first, progressive discovery, user-driven mapping)
- **Architectural Benefits**: How functional design patterns serve financial analysis needs

### 3. Real-World Examples Throughout
- Use actual companies (AAPL, AEO, GOOGL) in examples
- Show complete workflows, not isolated commands
- Demonstrate both successful analysis and error recovery patterns

## Manual Structure

### Part I: Understanding the Foundation
**Chapter 1: XBRL and Financial Data - A Gentle Introduction**
- What XBRL is and why it matters for analysts
- The chaos: thousands of companies, temporal variability, naming inconsistencies
- How EDGAR CLI transforms this complexity into manageable workflows

**Chapter 2: Core Concepts and Mental Models**
- Progressive discovery philosophy
- Cache-first architecture benefits
- Concept-driven vs role-driven analysis
- Pipeline thinking for financial analysis

### Part II: Essential Workflows
**Chapter 3: Getting Started - Your First Analysis**
- Installation and setup
- Basic company lookup and filing discovery
- Extracting your first financial statement
- Understanding the output formats

**Chapter 4: Discovery Patterns**
- Finding companies and filings
- Role exploration and pattern matching
- Concept discovery and filtering
- Building understanding of company-specific XBRL structures

**Chapter 5: Data Extraction Workflows**
- Single-company analysis patterns
- Multi-period comparisons
- Cross-company industry analysis
- Handling data quality and missing information

### Part III: Pipeline Mastery
**Chapter 6: Command Composition Patterns**
- Understanding the pipeline philosophy
- Filtering and transformation chains
- Output format routing (tables, CSV, JSON)
- Error handling in complex pipelines

**Chapter 7: Reproducible Research with Journals**
- Journal system fundamentals
- Creating curated analysis workflows
- Replay patterns for data refresh
- Collaborative workflow sharing
- Database regeneration strategies

### Part IV: Advanced Usage
**Chapter 8: Automation and Batch Processing**
- Environment variable configuration
- Scheduled refresh patterns
- Integration with external systems
- Performance optimization strategies

**Chapter 9: Troubleshooting and Edge Cases**
- Common XBRL structure variations
- Handling filing inconsistencies
- Network timeout recovery
- Database maintenance patterns

**Chapter 10: Extending and Customizing**
- Configuration options
- Custom analysis patterns
- Integration possibilities
- Contributing improvements

## Writing Guidelines

### Voice and Tone
- **Conversational but authoritative**: Like an experienced analyst teaching a colleague
- **Practical-first**: Every concept illustrated with working examples
- **Honest about complexity**: Acknowledge XBRL challenges while showing solutions

### Example Standards
- **Complete workflows**: Show full command sequences, not fragments
- **Real data**: Use actual company examples with realistic output
- **Error scenarios**: Include common failure cases and recovery strategies
- **Progressive examples**: Build complexity within each chapter

### Code and Command Formatting
- Use syntax highlighting for all command examples
- Show both input commands and expected output
- Include timing expectations ("This may take 30 seconds...")
- Explain status messages and progress indicators

## Key Themes to Emphasize

### 1. The Power of Progressive Discovery
How the tool turns XBRL's variability from a obstacle into a feature through guided exploration.

### 2. Journal-Driven Analysis
The revolutionary concept of journals as data pipeline specifications and the replay-as-refresh pattern.

### 3. Cache-First Efficiency
How intelligent caching transforms slow XBRL processing into fast iterative analysis.

### 4. Functional Composition
How simple commands compose into sophisticated financial analysis workflows.

### 5. Reproducible Research
How the tool enables sharing, validation, and automation of financial analysis methodologies.

## Success Metrics
A successful manual will enable users to:
1. **Immediate value**: Extract basic financial data within first session
2. **Conceptual mastery**: Understand XBRL challenges and tool solutions within first week
3. **Workflow proficiency**: Create custom analysis pipelines within first month
4. **Advanced automation**: Implement journal-driven refresh systems for ongoing research

## Future Considerations
- **Community contributions**: Structure to accommodate user-contributed examples
- **Version updates**: Framework for documenting new features and workflow patterns
- **Interactive elements**: Consideration for online/searchable versions
- **Video supplements**: Potential for screencast demonstrations of complex workflows