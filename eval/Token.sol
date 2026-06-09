// SPDX-License-Identifier: MIT
pragma solidity ^0.7.0;

contract Vault {
    mapping(address => uint) public balances;
    address owner;

    constructor() { owner = msg.sender; }

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint amount) public {
        require(balances[msg.sender] >= amount);
        (bool success,) = msg.sender.call{value: amount}("");
        balances[msg.sender] -= amount;
    }

    function transfer(address to, uint amount) public {
        require(tx.origin == owner);
        balances[to] += amount;
        balances[msg.sender] -= amount;
    }
}
