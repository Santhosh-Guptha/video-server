# QA Test Strategy Document
**Project**: Enterprise Video Management System (VMS)  
**Owner**: QA Lead  

---

## 1. Testing Phases
- **Unit Testing**: Validate routing and dynamic stream resolution functions.
- **Integration Testing**: Verify safety-net filesystem index updates using `test_indexer_pruning.py`.
- **Load Testing**: Simulate 50 concurrent WebRTC viewer players and verify CPU load limits.
