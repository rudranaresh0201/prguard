pragma solidity ^0.8.0;
contract Token {
    address owner;
    mapping(address => uint256) balances;

    function transfer(address to, uint256 amount) public {
        require(tx.origin == owner, "Not owner");
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }

    function withdraw() public {
        uint256 amount = balances[msg.sender];
        (bool success, ) = msg.sender.call{value: amount}("");
        balances[msg.sender] = 0;
    }
}
